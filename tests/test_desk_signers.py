"""Signer guards: caps, key handling, approvals, and never broadcasting by accident.

The broadcast path itself cannot be tested here — it needs a live chain — so
these cover everything around it: the rails that decide whether a send happens
at all, and the arithmetic that would misprice an order if it were wrong.
"""
import json

import pytest

from trading_desk.execution.signers import (
    EVM_KEY_ENV,
    SOLANA_KEY_ENV,
    EvmSigner,
    KeyLoadError,
    MultiChainSigner,
    SignerError,
    SignerLimits,
    SolanaSigner,
)
from trading_desk.models import Chain

# A throwaway key with no funds, used only to exercise address derivation.
TEST_EVM_KEY = "0x" + "11" * 32


# ------------------------------------------------------------------- limits


def test_orders_above_the_signer_cap_are_refused():
    """Defence in depth: the signer caps size independently of the risk config."""
    limits = SignerLimits(max_order_usd=25.0)
    limits.check(24.99)
    with pytest.raises(SignerError, match="exceeds the signer's hard cap"):
        limits.check(25.01)


def test_an_unknown_order_size_is_not_silently_allowed_past_the_cap():
    # None means "not provided" — the cap simply cannot apply, and the desk's
    # own sizing is the remaining control. Documented rather than guessed at.
    SignerLimits(max_order_usd=1.0).check(None)


def test_dry_run_and_simulation_are_on_by_default():
    limits = SignerLimits()
    assert limits.dry_run is True
    assert limits.simulate_before_send is True


# ---------------------------------------------------------------- key safety


def test_a_missing_solana_key_is_reported_without_guessing(monkeypatch):
    monkeypatch.delenv(SOLANA_KEY_ENV, raising=False)
    with pytest.raises(KeyLoadError, match=SOLANA_KEY_ENV):
        SolanaSigner().wallet_address()


def test_a_missing_evm_key_is_reported(monkeypatch):
    monkeypatch.delenv(EVM_KEY_ENV, raising=False)
    with pytest.raises(KeyLoadError, match=EVM_KEY_ENV):
        EvmSigner().wallet_address()


def test_a_malformed_key_error_never_quotes_the_key(monkeypatch):
    """An error message that echoes the key would leak it into every log."""
    secret = "definitely-not-a-valid-private-key-but-still-secret"
    monkeypatch.setenv(EVM_KEY_ENV, secret)

    with pytest.raises(KeyLoadError) as exc:
        EvmSigner().wallet_address()

    assert secret not in str(exc.value)
    assert "not a valid EVM private key" in str(exc.value)


def test_a_valid_key_derives_its_address(monkeypatch):
    monkeypatch.setenv(EVM_KEY_ENV, TEST_EVM_KEY)
    address = EvmSigner().wallet_address()
    assert address.startswith("0x") and len(address) == 42


def test_repr_never_exposes_key_material(monkeypatch):
    monkeypatch.setenv(EVM_KEY_ENV, TEST_EVM_KEY)
    signer = EvmSigner()
    signer.wallet_address()

    assert "REDACTED" in repr(signer)
    assert TEST_EVM_KEY not in repr(signer)
    assert TEST_EVM_KEY not in str(signer)


def test_a_json_array_solana_key_is_accepted_as_a_format(monkeypatch):
    """solana-keygen files are JSON byte arrays; a wrong-length one still fails."""
    monkeypatch.setenv(SOLANA_KEY_ENV, json.dumps([1, 2, 3]))
    with pytest.raises(KeyLoadError) as exc:
        SolanaSigner().wallet_address()
    # Either solders is absent or the key is rejected — never silently accepted.
    assert "solders" in str(exc.value) or "not a valid Solana secret key" in str(exc.value)


# ------------------------------------------------------------ chain routing


def test_a_signer_refuses_a_chain_it_does_not_hold_keys_for():
    with pytest.raises(SignerError, match="cannot sign for"):
        SolanaSigner().sign_and_send(Chain.BNB, {})
    with pytest.raises(SignerError, match="configured for BNB Chain"):
        EvmSigner().sign_and_send(Chain.SOLANA, {})


def test_multichain_signer_routes_by_chain(monkeypatch):
    monkeypatch.setenv(EVM_KEY_ENV, TEST_EVM_KEY)
    evm = EvmSigner()
    signer = MultiChainSigner({Chain.BNB: evm})

    assert signer.wallet_address(Chain.BNB) == evm.wallet_address()
    with pytest.raises(SignerError, match="no signer configured for Solana"):
        signer.wallet_address(Chain.SOLANA)


def test_a_payload_without_a_transaction_is_refused(monkeypatch):
    monkeypatch.setenv(EVM_KEY_ENV, TEST_EVM_KEY)
    with pytest.raises(SignerError, match="missing the transaction"):
        EvmSigner().sign_and_send(Chain.BNB, {"transaction": {}})


def test_a_solana_payload_without_a_quote_is_refused():
    with pytest.raises(SignerError, match="quote missing"):
        SolanaSigner().sign_and_send(Chain.SOLANA, {})


# --------------------------------------------------- EVM send path, faked RPC


class _FakeEth:
    def __init__(self, allowance=0, chain_id=56):
        self.allowance = allowance
        self.chain_id = chain_id
        self.gas_price = 3_000_000_000
        self.sent = []
        self.calls = []

    def get_transaction_count(self, address):
        return 7

    def estimate_gas(self, tx):
        return 210_000

    def call(self, tx):
        self.calls.append(tx)
        return b""

    def contract(self, address=None, abi=None):
        return _FakeContract(self.allowance)

    def send_raw_transaction(self, raw):
        self.sent.append(raw)

        class _Hash:
            def hex(self_inner):
                return "0xsent"

        return _Hash()


class _FakeContract:
    def __init__(self, allowance):
        self._allowance = allowance
        self.functions = self

    def decimals(self):
        return _Call(18)

    def allowance(self, owner, spender):
        return _Call(self._allowance)

    def approve(self, spender, amount):
        return _Call(None, tx={"to": "0x" + "22" * 20, "data": "0xabcdef02", "value": 0})


class _Call:
    def __init__(self, value, tx=None):
        self._value = value
        self._tx = tx

    def call(self):
        return self._value

    def build_transaction(self, params):
        return {**(self._tx or {}), **params}


class _FakeWeb3:
    def __init__(self, allowance=0):
        self.eth = _FakeEth(allowance=allowance)


BUY_PAYLOAD = {
    "transaction": {"to": "0x" + "33" * 20, "data": "0xabcdef01", "value": 1000, "gas": 250000},
    "usd_amount": 10.0,
}


def test_a_dry_run_simulates_but_broadcasts_nothing(monkeypatch):
    monkeypatch.setenv(EVM_KEY_ENV, TEST_EVM_KEY)
    web3 = _FakeWeb3()
    signer = EvmSigner(web3=web3, limits=SignerLimits(dry_run=True))

    ref = signer.sign_and_send(Chain.BNB, BUY_PAYLOAD)

    assert ref == "dryrun:evm:not-broadcast"
    assert web3.eth.sent == []  # nothing left the machine
    assert web3.eth.calls  # but it was simulated


def test_arming_broadcasts(monkeypatch):
    monkeypatch.setenv(EVM_KEY_ENV, TEST_EVM_KEY)
    web3 = _FakeWeb3()
    signer = EvmSigner(web3=web3, limits=SignerLimits(dry_run=False))

    assert signer.sign_and_send(Chain.BNB, BUY_PAYLOAD) == "0xsent"
    assert len(web3.eth.sent) == 1


def test_a_reverting_transaction_is_not_sent(monkeypatch):
    monkeypatch.setenv(EVM_KEY_ENV, TEST_EVM_KEY)
    web3 = _FakeWeb3()

    def explode(tx):
        raise RuntimeError("execution reverted: TRANSFER_FROM_FAILED")

    web3.eth.call = explode
    signer = EvmSigner(web3=web3, limits=SignerLimits(dry_run=False))

    with pytest.raises(SignerError, match="reverted in simulation"):
        signer.sign_and_send(Chain.BNB, BUY_PAYLOAD)
    assert web3.eth.sent == []


def test_the_signer_cap_blocks_an_oversized_order(monkeypatch):
    monkeypatch.setenv(EVM_KEY_ENV, TEST_EVM_KEY)
    web3 = _FakeWeb3()
    signer = EvmSigner(web3=web3, limits=SignerLimits(dry_run=False, max_order_usd=5.0))

    with pytest.raises(SignerError, match="hard cap"):
        signer.sign_and_send(Chain.BNB, {**BUY_PAYLOAD, "usd_amount": 500.0})
    assert web3.eth.sent == []


def test_a_buy_needs_no_approval(monkeypatch):
    """Buys spend the native asset, so no ERC-20 allowance is involved."""
    monkeypatch.setenv(EVM_KEY_ENV, TEST_EVM_KEY)
    web3 = _FakeWeb3()
    signer = EvmSigner(web3=web3, limits=SignerLimits(dry_run=False))

    assert "," not in signer.sign_and_send(Chain.BNB, BUY_PAYLOAD)


def test_a_sell_without_allowance_approves_first(monkeypatch):
    """A position that cannot be approved is a position that cannot be exited."""
    monkeypatch.setenv(EVM_KEY_ENV, TEST_EVM_KEY)
    web3 = _FakeWeb3(allowance=0)
    signer = EvmSigner(web3=web3, limits=SignerLimits(dry_run=False))

    ref = signer.sign_and_send(
        Chain.BNB,
        {
            "transaction": {"to": "0x" + "33" * 20, "data": "0xabcdef01", "gas": 250000,
                            "allowanceTarget": "0x" + "44" * 20},
            "sell_token": "0x" + "55" * 20,
            "sell_amount": 1_000_000,
            "usd_amount": 10.0,
        },
    )

    assert ref.count(",") == 1  # approval hash, then swap hash
    assert len(web3.eth.sent) == 2


def test_an_existing_allowance_skips_the_approval(monkeypatch):
    monkeypatch.setenv(EVM_KEY_ENV, TEST_EVM_KEY)
    web3 = _FakeWeb3(allowance=10**30)
    signer = EvmSigner(web3=web3, limits=SignerLimits(dry_run=False))

    ref = signer.sign_and_send(
        Chain.BNB,
        {
            "transaction": {"to": "0x" + "33" * 20, "data": "0xabcdef01", "gas": 250000,
                            "allowanceTarget": "0x" + "44" * 20},
            "sell_token": "0x" + "55" * 20,
            "sell_amount": 1_000_000,
            "usd_amount": 10.0,
        },
    )

    assert "," not in ref
    assert len(web3.eth.sent) == 1


def test_decimals_are_read_from_the_chain_and_cached(monkeypatch):
    monkeypatch.setenv(EVM_KEY_ENV, TEST_EVM_KEY)
    signer = EvmSigner(web3=_FakeWeb3())

    assert signer.token_decimals(Chain.BNB, "0x" + "55" * 20) == 18
    assert signer._decimals_cache  # second call does not hit the chain


# ---------------------------------------------------- how the key is stored
#
# This is the exposure that actually drains a wallet. A broken-into dashboard
# can at worst sell positions back into your own wallet — the desk has no
# function that sends funds to an address. Whoever reads the key file owns the
# wallet outright, from anywhere, forever.


def test_a_world_readable_key_file_is_critical(tmp_path):
    from trading_desk.execution.signers import audit_key_storage

    env = tmp_path / ".env"
    env.write_text("DESK_EVM_PRIVATE_KEY=0xdead")
    env.chmod(0o644)

    findings = audit_key_storage(env)
    assert any(f.blocking and "other accounts" in f.message for f in findings)


def test_a_locked_down_key_file_passes(tmp_path, monkeypatch):
    from trading_desk.execution.signers import EVM_KEY_ENV, SOLANA_KEY_ENV, audit_key_storage

    monkeypatch.delenv(EVM_KEY_ENV, raising=False)
    monkeypatch.delenv(SOLANA_KEY_ENV, raising=False)
    env = tmp_path / ".env"
    env.write_text("DESK_EVM_PRIVATE_KEY=0xdead")
    env.chmod(0o600)

    assert audit_key_storage(env) == []


def test_a_key_in_a_synced_folder_is_critical(tmp_path):
    """A key in Dropbox is a key in a cloud account and on every synced device."""
    from trading_desk.execution.signers import audit_key_storage

    synced = tmp_path / "Dropbox" / "desk"
    synced.mkdir(parents=True)
    env = synced / ".env"
    env.write_text("DESK_EVM_PRIVATE_KEY=0xdead")
    env.chmod(0o600)

    findings = audit_key_storage(env)
    assert any(f.blocking and "synced folder" in f.message for f in findings)


def test_a_key_in_an_unignored_git_repo_is_critical(tmp_path):
    """One `git push` would publish the wallet."""
    from trading_desk.execution.signers import audit_key_storage

    (tmp_path / ".git").mkdir()
    (tmp_path / ".gitignore").write_text("__pycache__/\n")
    env = tmp_path / ".env"
    env.write_text("DESK_EVM_PRIVATE_KEY=0xdead")
    env.chmod(0o600)

    findings = audit_key_storage(env)
    assert any(f.blocking and "git repository" in f.message for f in findings)


def test_an_ignored_key_in_a_repo_is_fine(tmp_path, monkeypatch):
    from trading_desk.execution.signers import EVM_KEY_ENV, SOLANA_KEY_ENV, audit_key_storage

    monkeypatch.delenv(EVM_KEY_ENV, raising=False)
    monkeypatch.delenv(SOLANA_KEY_ENV, raising=False)
    (tmp_path / ".git").mkdir()
    (tmp_path / ".gitignore").write_text("__pycache__/\n.env\n")
    env = tmp_path / ".env"
    env.write_text("DESK_EVM_PRIVATE_KEY=0xdead")
    env.chmod(0o600)

    assert audit_key_storage(env) == []


def test_no_key_file_yet_is_not_a_finding(tmp_path):
    from trading_desk.execution.signers import audit_key_storage

    assert audit_key_storage(tmp_path / ".env") == []


def test_this_repo_ignores_its_own_key_file():
    """Regression: the shipped .gitignore must cover .env."""
    from pathlib import Path

    assert ".env" in Path(".gitignore").read_text().splitlines()


def test_the_desk_has_no_function_that_sends_funds_to_an_address():
    """The property that makes a compromised dashboard survivable.

    If a transfer/withdraw path is ever added, this fails — and the security
    story in the README stops being true.
    """
    import re
    from pathlib import Path

    banned = re.compile(r"\b(def\s+\w*(withdraw|transfer_out|send_funds|sweep)\w*)\b")
    for path in Path("trading_desk").rglob("*.py"):
        assert not banned.search(path.read_text()), f"{path} defines a fund-moving function"
