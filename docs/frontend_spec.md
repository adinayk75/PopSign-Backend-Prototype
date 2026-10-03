# Frontend Reference Captured from the PopSign Figma Screens

This file preserves the supplied October 3, 2026 Figma direction so the implementation does not depend on chat history.

## Core screens

1. **Generate Story**
   - centered title and helper text
   - open prompt entry as the primary demo path
   - theme and difficulty selections
   - large rounded Generate button
2. **Storybook Library**
   - search bar
   - Your Collection / Explore control
   - two-column book cards
3. **Story Selection**
   - cover art
   - difficulty and author
   - Start Learning button
4. **Story Reader**
   - page count, story title, and illustration
   - sentence with previous/next navigation
   - ASL word chips separated by plus signs
   - selected word highlighted in blue
   - Sign Info panel and signer/video panel
   - turtle/rabbit speed control
   - Info, Grammar, and Return to Phrase controls
5. **Persistent navigation**
   - Home, Sign Look, Books, Review
   - Books appears selected throughout the story flow

## Prototype interaction

- Tapping the ambiguous word reruns contextual matching.
- Moving between pages 1 and 2 demonstrates two meanings of `can` and therefore two video keys.
- Sign Info displays the proposed sense, definition, top cosine score, and runner-up margin.
- Unclear context must show `Needs review`; it must not silently choose a default sign.
- Actual videos remain local. Until media is attached, the video panel displays a signer placeholder and selected `video_key`.

## Visual language

- mobile-first white canvas
- near-black typography
- light gray rounded cards and controls
- teal-blue selection/accent color
- simple illustrated story art
- large readable sentence text
- generous spacing suitable for children and classroom use

The current `web/` implementation follows this specification with original local SVG placeholders so it runs without external image services.
