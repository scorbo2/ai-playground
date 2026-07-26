# Match 3 - new feature

In this directory you will find a `Match3.py` containing an implementation of a "match 3" board game. 
The game board is an 8x8 grid where each cell contains one token. The player must attempt to swap
adjacent tokens in order to create horizontal or vertical runs of three or more tokens of the same
color. Red token matches deduct points, all other token colors add points. Once the player hits a
certain point threshold, the level is won, and the board resets for the next level.

## New feature - magical tokens

Your task is to add two new "magical" token types. These look like regular tokens of one of the
usual token colors, except that they have a white stripe overlaid on them:

- *horizontal magical tokens* have a horizontal white stripe of 8px thickness running through the middle
  of the token. Matching this token will clear all tokens in the row where the match occurred.
- *vertical magical tokens* have a vertical white stripe of 8px thickness running through the middle
  of the token. Matching this token will clear all tokens in the column where the match occurred.

Magical tokens have a 0.5% chance of spawning whenever new tokens appear (this includes the initial
board setup at the start of each level). This percentage chance of spawning increases by 0.5% each time
a successful match occurs (regardless of match color). When a new magical token spawns, the chance for
the next magical token to spawn resets to 0.5%. At the successful conclusion of each level, the chance of a magical
token spawning resets to 0.5%.

When the player successfully matches a "magical token", the text "MAGICAL POWER!" should appear briefly
on the screen in large semi-transparent dark red font, similar to how text messages are displayed
for other game events.

In addition to the usual scoring rules for making a successful match, the player receives +1 point for each
non-red token in the row or column in question, and -1 points for each red token in the row or column in question.

## Magical token chaining

It's possible that the user will match a horizontal magical token in a row that also contains a vertical magical
token, or vice versa. In that case, the effect of the other magical token should also trigger.

For example, the user complets a match with a horizontal magical token on row 5 at position 5. This row also
happens to contain a magical vertical token at position 1. The result should be that all tokens in row 5 are
cleared from the board, AND all tokens in column 1 should be cleared. 

In the case where the user matches a horizontal magical token in a row that contains additional horizontal magical
tokens, the effects are redundant, so no additional effect is triggered. Likewise, if the user matches a vertical
magical token in a column that contains other vertical magical tokens, no additional effect is triggered.


