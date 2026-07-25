# Match 3

## Game Overview

This is a simple game that starts with a game board divided into 8 rows of 8 square cells.
Each cell contains a circular token in one of six colors: red, green, blue, orange, yellow, and pink.
When three or more tokens of the same color align either horizontally or vertically, that is
considered a "match", and those tokens are removed from the board. (Diagonal adjacency is not considered).
When tokens are removed, all tokens above the now-empty cells move down by one cell, and additional
random tokens are inserted as needed from the top of the board, such that every cell on the board always
contains one token after each move. The player scores points for successfully matching and removing
tokens. Green, blue, orange, yellow, and pink tokens are worth 1 point each. Red tokens are considered "bad",
and matching them substracts one point each. The player must therefore use tactics to try to avoid matching
red tokens during play. When a certain score threshold is reached, the level is complete, the board resets,
and play resumes at a higher level, with a higher score threshold. There is no final level - the game continues
until the user exits.

## Graphics

### Game board

The game board has a thick dark gray border, and consists of 8 rows of 8 tokens each.
Each cell is square, measuring 60px by 60px, and each cell has a thin light gray border and a black interior background. 
The screen background behind the game board is a solid light pastel blue color.

Cell selection is indicated by changing the cell border color to light green, and changing the cell background fill
color to dark green. 

Cell movement options are indicated by changing the cell border color to light green, and changing the cell
background color to dark gray.

### Title bar

A non-interactive title bar appears above the game board, with the text "MATCH 3" centered in white
text on a black background. The title bar has a thick dark gray border, and is vertically separated from 
the game board by 40px.

### Side bar

A vertically-oriented side bar is displayed to the right of the game board. The game board and side bar
are separated by 40px. This bar displays the current 1-based level number,
the player's current score, and the current level's target threshold. 
A "restart" button should be offered which abandons the current game and starts 
a new game at level 1.

The side bar has a width of 200px and its height should match the game board. The side bar has a thick 
dark gray border and a black interior background. Text labels should appear in white text.

### Tokens

Tokens are circles with a diameter of 50px, centered inside their cell. Tokens have a thin white border,
and a solid fill color. Token colors should NOT be pastel, because pastel colors are harder to differentiate.
Choose colors with good chromatic separation.

### Layout

The game board, side bar, and title bar are centered in the display. The title bar's left border aligns
with the game board's left border, and the title bar's right border aligns with the side bar's right border.
There is no footer element.

## Playing the game

Each level must start with all cells containing one token, with no horizontal or vertical runs of more 
than 2 tokens of the same color. There is no time limit or clock displayed. The player can click any cell
to select it. The immediate horizontal and vertical neighbors of the selected cell become movement options.
There is NO board wrap. That is, clicking a cell in the leftmost column does NOT indicate a cell in the 
rightmost column of the same row as a movement option. Clicking a cell that is already selected should
deselect that cell, causing it and its immediate horizontal and vertical neighbors to revert to their
default border and fill colors.

Once a cell is selected, the player can click any movement option cell to swap the tokens between the selected
cell and the chosen movement option cell. The swap ONLY occurs if the move is valid. A move is only valid if
the proposed token swap would result in a horizontal or vertical formation of three or more tokens of the same
color. If the proposed swap is not valid, the selected cell and the chosen movement option cell should 
temporarily flash red: their borders change to light red, and their background fill colors change to dark red.
After 300ms, their colors revert back. This indicates that the proposed move is not valid. The selected cell
remains selected after indicating an invalid move, and the immediately neighboring cells are still shown
as movement options.

If the proposed movement is valid, the tokens are swapped. Token movement should be animated instead of 
instantaneous. During animation, no mouse input is allowed on the game board. The movement animation should not
take longer than 500ms. Once the token swap animation completes, all newly-formed horizontally or vertically contiguous
groups of three or more tokens of the same color are removed from the board. The player's score is updated
according to the scoring rules, and then all tokens above the now-empty cells "fall" to fill the empty cells
on the game board as needed. New random tokens then "fall" from the top of the board to fill the empty cells at the 
tops of the affected columns. This "falling" should also be animated.

Implementation suggestion: maintain a single 2D array as the sole source of truth for board state (token colors).
After any match, gravity should be resolved per-column by extracting all remaining non-null tokens in order, 
then rebuilding the column as new random tokens on top followed by the extracted tokens below — rather than 
shifting cells one at a time. All rendering (including the selected/movement-option highlight state) 
should be derived from this array on each update rather than mutated incrementally, so that no rendering 
state can go stale relative to the underlying board.

## Advancing levels

Level 1 has a score threshold of 100 points. When this threshold is met or exceeded, the text
"LEVEL COMPLETE!" appears in large opaque light blue font over the game board. This should replace
any other text that is currently showing. This "LEVEL COMPLETE!" text remains
visible for 2s (no mouse input is allowed during this period, and all animation stops during this period).
The board then "resets", all cells revert to non-selected status, and the next level begins. Each level
adds 50 to the score threshold required to advance to the next level. The text "BEGIN LEVEL N" should
briefly appear over the game board in large opaque pink font, where N is the 1-based level number.

The player's score resets to 0 on each new level. 

It is possible for the player's score to go negative, due to matching too many red tokens! Do not assume
that the player's score will always be a positive number. if the value goes negative, the label text
showing the player's score in the sidebar should change from white to light red. It should revert to white
once the score is once again greater than or equal to zero.

### Chained removals

As tokens "fall" into place to fill voids left by successful removal, it's possible that additional horizontal
and/or vertical chains of three or more same-color tokens will be formed. These also count as successful removals
and follow the same animation rules as a regular removal. However, such "chained" removals have double the point
value of a regular removal. This doubling effect can stack, if yet another three-or-more grouping is formed
as a result of the removal. The text "NICE!" should briefly flash in semi-transparent large white font on top
of the game board (unless the matched tokens were red). There is no upper limit to this 2x chaining bonus!

If a chained match leads to another chained match, the text message "NICE!" should change accordingly:

- on a third chained match: "VERY NICE!" in semi-transparent large orange font
- on a fourth changed match: "AMAZING!!" in semi-transparent large green font
- on a fifth or subsequent chained match: "HOLY COW!" in semi-transparent very large light blue font

### Matching more than 3 tokens

Contiguous token groups (horizontal or vertical) consisting of more than 3 tokens are worth 1 extra point per token
for each additional token in the group. For example, matching 4 tokens at once would earn the player 5 points (one
point per token removed plus one extra point for matching a group of 4). Matching 5 tokens would earn the player
7 points (one point per token removed, plus two points for an extra long group). The text "BONUS!" should briefly
flash in semi-transparent large green font on top of the game board (unless the matched tokens were red).

### Matching more than one group at a time

It's possible for a single token swap to generate two separate-color groups of three or more tokens. There are 
no special scoring rules for such a multi-match. But, the text "MULTI-MATCH!" should briefly appear in large
semi-transparent light blue font on top of the game board.

### Matching red tokens

Red tokens are considered "bad". Matching three or more horizontally or vertically adjacent red tokens
should briefly change the game board's border to dark red. The text "OH NO!" should briefly flash in semi-transparent
large light red font on top of the game board.

Each red token removed from the board counts as -1 points towards the user's score. The bonus points described
for chained removals and more-than-3 removals also apply to red tokens, but in negative points instead of
positive points. 

### Match animation

When a contiguous group of tokens is matched, 40 colorful particles should emit from the center of each
matched cell in an "explosion" pattern. These particles should quickly fade by modifying their alpha values
until they are fully invisible. The particle explosion animation can run concurrently with the token removal
and "falling" animation.

Note: as soon as a match animation begins, cancel any cell selection or movement option highlighting by reverting
all cells to their normal border/fill colors. No cell is considered selected after a successful match.

### Never block the reset button

During animation, the game board should disallow mouse input on the game board. But the "reset" button in
the side bar should **never** be blocked. The user can click "reset" at any time, even if an animation is in
progress. Clicking reset cancels all animations in progress, removes any displayed text, and resets the board
immediately. Resetting the board also cancels any current cell selection. The player's score reverts to 0 and
play begins again at level 1.

### Text animation

Whenever text needs to briefly appear over the game board (example: "BONUS!", "MULTI-MATCH!", "OH NO!", etc),
the text should appear centered over the game board, but move upwards at a rate of around 40px/second.
The text should fade out after no more than 2s. This smooths the problem of multiple text messages appearing
in rapid succession.

Exceptions to this rule:
- "LEVEL COMPLETE!"
- "NO MOVES - GAME OVER"

These messages are special, and should always appear exactly centered and unmoving. If either of these
special messages are displayed, all other text messages should be hidden immediately, 
and any animation in progress should be stopped.

## Unsolvable boards

It's possible for the game board to enter a state where there are no valid moves. This ends the game.
Show the text "NO MOVES - GAME OVER" in large opaque light red text over the game board.
The only option for the user at this point is to click the "reset" button.

## Game format

The game should exist as a single, self-contained Html file. Use vanilla JS, CSS Grid/Flexbox for layout,
and requestAnimationFrame or CSS transitions for animations. Do not use external libraries.
The game has no audio.

