/* Generated from ../script.json by render/build.sh - do not edit. */
window.SCRIPT = {
  "meta": {
    "title": "Animal Sounds Song",
    "subtitle": "Sing Along with the Animal Friends",
    "width": 1920,
    "height": 1080,
    "fps": 30,
    "bpm": 120,
    "language": "en"
  },
  "scenes": [
    {
      "id": "intro",
      "type": "intro",
      "dur": 12,
      "bg": { "sky": ["#4cc9f0", "#c8f4ff"], "hills": ["#77dd8f", "#4cbf6a", "#2f9c4e"], "accent": "#ffd23f", "frame": "#ff6b6b" },
      "captions": [
        { "t": 0.6, "d": 3.6, "text": "Welcome to the Animal Sounds Song!" },
        { "t": 4.5, "d": 3.5, "text": "Can you make the sounds with me?" },
        { "t": 8.3, "d": 3.4, "text": "Let's go! Here we go!" }
      ]
    },

    {
      "id": "cow", "type": "verse", "animal": "cow", "name": "cow", "sound": "Moo", "dur": 12,
      "bg": { "sky": ["#5bc8f5", "#d6f6ff"], "hills": ["#8ce38f", "#57c46d", "#329b4d"], "accent": "#fff06b", "frame": "#f26c6c" },
      "captions": [
        { "t": 0.3, "d": 2.7, "text": "Here comes the cow!" },
        { "t": 3.2, "d": 2.8, "text": "The cow says: MOO! MOO!" },
        { "t": 6.2, "d": 2.8, "text": "Can you say MOO?" },
        { "t": 9.2, "d": 2.6, "text": "MOO! MOO! MOO!" }
      ]
    },
    {
      "id": "duck", "type": "verse", "animal": "duck", "name": "duck", "sound": "Quack", "dur": 12,
      "bg": { "sky": ["#49d0d8", "#d9fbff"], "hills": ["#6fdca8", "#3fc38c", "#25976a"], "accent": "#ffd23f", "frame": "#2fa8c9", "water": true },
      "captions": [
        { "t": 0.3, "d": 2.7, "text": "Look! A little yellow duck!" },
        { "t": 3.2, "d": 2.8, "text": "The duck says: QUACK! QUACK!" },
        { "t": 6.2, "d": 2.8, "text": "Can you say QUACK?" },
        { "t": 9.2, "d": 2.6, "text": "QUACK! QUACK! QUACK!" }
      ]
    },
    {
      "id": "cat", "type": "verse", "animal": "cat", "name": "cat", "sound": "Meow", "dur": 12,
      "bg": { "sky": ["#b98cf0", "#ffd8f0"], "hills": ["#f79bd0", "#e173b8", "#b84f92"], "accent": "#ffe066", "frame": "#a259d9" },
      "captions": [
        { "t": 0.3, "d": 2.7, "text": "Hello, little orange cat!" },
        { "t": 3.2, "d": 2.8, "text": "The cat says: MEOW! MEOW!" },
        { "t": 6.2, "d": 2.8, "text": "Can you say MEOW?" },
        { "t": 9.2, "d": 2.6, "text": "MEOW! MEOW! MEOW!" }
      ]
    },
    {
      "id": "dog", "type": "verse", "animal": "dog", "name": "dog", "sound": "Woof", "dur": 12,
      "bg": { "sky": ["#5fbdf5", "#e2f4ff"], "hills": ["#9be07c", "#63c45c", "#3b9a41"], "accent": "#ffb84d", "frame": "#f2994a" },
      "captions": [
        { "t": 0.3, "d": 2.7, "text": "Who is that? It's the dog!" },
        { "t": 3.2, "d": 2.8, "text": "The dog says: WOOF! WOOF!" },
        { "t": 6.2, "d": 2.8, "text": "Can you say WOOF?" },
        { "t": 9.2, "d": 2.6, "text": "WOOF! WOOF! WOOF!" }
      ]
    },
    {
      "id": "frog", "type": "verse", "animal": "frog", "name": "frog", "sound": "Ribbit", "dur": 12,
      "bg": { "sky": ["#54d6c0", "#dcfff6"], "hills": ["#7fe3a0", "#42c47f", "#26965c"], "accent": "#c9f24d", "frame": "#3cb371", "water": true },
      "captions": [
        { "t": 0.3, "d": 2.7, "text": "Hop, hop! It's the frog!" },
        { "t": 3.2, "d": 2.8, "text": "The frog says: RIBBIT! RIBBIT!" },
        { "t": 6.2, "d": 2.8, "text": "Can you say RIBBIT?" },
        { "t": 9.2, "d": 2.6, "text": "RIBBIT! RIBBIT! RIBBIT!" }
      ]
    },
    {
      "id": "lion", "type": "verse", "animal": "lion", "name": "lion", "sound": "Roar", "dur": 12,
      "bg": { "sky": ["#ffb648", "#ffe9b0"], "hills": ["#f2c14e", "#e0a63c", "#b8792c"], "accent": "#ff8c42", "frame": "#e07b39" },
      "captions": [
        { "t": 0.3, "d": 2.7, "text": "Meet the big, brave lion!" },
        { "t": 3.2, "d": 2.8, "text": "The lion says: ROAR! ROAR!" },
        { "t": 6.2, "d": 2.8, "text": "Can you say ROAR?" },
        { "t": 9.2, "d": 2.6, "text": "ROAR! ROAR! ROAR!" }
      ]
    },
    {
      "id": "monkey", "type": "verse", "animal": "monkey", "name": "monkey", "sound": "Ooh ooh ah ah", "dur": 12,
      "bg": { "sky": ["#3fc9a0", "#d4fff0"], "hills": ["#6bd47f", "#38ab5e", "#1f7d43"], "accent": "#ffd23f", "frame": "#2d9c62", "jungle": true },
      "captions": [
        { "t": 0.3, "d": 2.7, "text": "Swing, swing! Monkey time!" },
        { "t": 3.2, "d": 2.8, "text": "The monkey says: OOH OOH AH AH!" },
        { "t": 6.2, "d": 2.8, "text": "Can you say OOH OOH AH AH?" },
        { "t": 9.2, "d": 2.6, "text": "OOH OOH AH AH!" }
      ]
    },
    {
      "id": "elephant", "type": "verse", "animal": "elephant", "name": "elephant", "sound": "Toot", "dur": 12,
      "bg": { "sky": ["#6aa9f0", "#dbeeff"], "hills": ["#8fd9a8", "#57b87e", "#2f8a58"], "accent": "#ffd6f0", "frame": "#7b8cde" },
      "captions": [
        { "t": 0.3, "d": 2.7, "text": "The big elephant is here!" },
        { "t": 3.2, "d": 2.8, "text": "The elephant says: TOOT! TOOT!" },
        { "t": 6.2, "d": 2.8, "text": "Can you say TOOT?" },
        { "t": 9.2, "d": 2.6, "text": "TOOT! TOOT! TOOT!" }
      ]
    },

    {
      "id": "guess-cow", "type": "guess", "animal": "cow", "name": "cow", "sound": "Moo", "dur": 8,
      "bg": { "sky": ["#7a5cf0", "#c9b8ff"], "hills": ["#7fe0a0", "#4cc07a", "#2d9455"], "accent": "#ffd23f", "frame": "#6a4bd6" },
      "captions": [
        { "t": 0.3, "d": 3.3, "text": "Guess who? Who says MOO?" },
        { "t": 4.0, "d": 3.7, "text": "It's the COW! MOO! MOO!" }
      ]
    },
    {
      "id": "guess-duck", "type": "guess", "animal": "duck", "name": "duck", "sound": "Quack", "dur": 8,
      "bg": { "sky": ["#f06fa8", "#ffd6ea"], "hills": ["#7fe0c0", "#42c4a0", "#26967a"], "accent": "#ffe066", "frame": "#e0559a" },
      "captions": [
        { "t": 0.3, "d": 3.3, "text": "Guess who? Who says QUACK?" },
        { "t": 4.0, "d": 3.7, "text": "It's the DUCK! QUACK! QUACK!" }
      ]
    },
    {
      "id": "guess-lion", "type": "guess", "animal": "lion", "name": "lion", "sound": "Roar", "dur": 8,
      "bg": { "sky": ["#ff8f5c", "#ffe3c9"], "hills": ["#f2c14e", "#dba03c", "#b0742a"], "accent": "#ffd23f", "frame": "#e8703a" },
      "captions": [
        { "t": 0.3, "d": 3.3, "text": "Guess who? Who says ROAR?" },
        { "t": 4.0, "d": 3.7, "text": "It's the LION! ROAR! ROAR!" }
      ]
    },
    {
      "id": "guess-frog", "type": "guess", "animal": "frog", "name": "frog", "sound": "Ribbit", "dur": 8,
      "bg": { "sky": ["#42b8e8", "#d6f4ff"], "hills": ["#7fe3a0", "#42c47f", "#26965c"], "accent": "#c9f24d", "frame": "#2f9fd0" },
      "captions": [
        { "t": 0.3, "d": 3.3, "text": "Guess who? Who says RIBBIT?" },
        { "t": 4.0, "d": 3.7, "text": "It's the FROG! RIBBIT! RIBBIT!" }
      ]
    },

    {
      "id": "chorus", "type": "chorus", "dur": 16,
      "bg": { "sky": ["#ff9ecb", "#ffe9a8"], "hills": ["#8ce38f", "#57c46d", "#329b4d"], "accent": "#ffd23f", "frame": "#f2568c" },
      "captions": [
        { "t": 0.3, "d": 3.5, "text": "Let's sing with all our friends!" },
        { "t": 4.1, "d": 3.6, "text": "Moo, quack, meow, woof!" },
        { "t": 8.1, "d": 3.6, "text": "Ribbit, roar, ooh-ooh, toot!" },
        { "t": 12.1, "d": 3.6, "text": "We are the animal friends!" }
      ]
    },
    {
      "id": "outro", "type": "outro", "dur": 12,
      "bg": { "sky": ["#6ec6f5", "#ffe9c9"], "hills": ["#8ce38f", "#57c46d", "#329b4d"], "accent": "#ffd23f", "frame": "#4aa3e0" },
      "captions": [
        { "t": 0.4, "d": 3.5, "text": "You did it! Great job!" },
        { "t": 4.3, "d": 3.6, "text": "Thank you for watching!" },
        { "t": 8.3, "d": 3.4, "text": "See you next time! Bye bye!" }
      ]
    }
  ]
};
