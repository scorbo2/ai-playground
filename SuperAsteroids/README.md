# SuperAsteroids!

A clone of the classic "Asteroids" arcade game, but with some cool improvements and new features.

The point here is to employ proper spec-driven development instead of YOLO one-shotting a prompt and hoping for the best.

## The process

I started by outlining the requirements in painful detail: [SuperAsteroids.txt](SuperAsteroids.txt)

Then I took those requirements to Qwen 3.6 27B Q6 and asked it to come up with an
implementation plan broken into discrete stages. Each stage should produce a runnable
program that I can manually test. I also requested the addition of a `--test` flag
that Qwen could use to verify that the game at least starts up okay (this minimizes
the copy+pasting of error messages from the console that I might otherwise have to do).

[SuperAsteroids-implementationPlan.md](SuperAsteroids-implementationPlan.md)

## The result

A complete, playable game, coded up in one evening! 

Manual testing revealed minor problems here and there that were reported back to Qwen and
addressed before moving on to the next development stage. But by having clear stage boundaries
with clear testing goals, we were able to lock down each stage one by one until the whole
game was complete.

TODO insert video link once it's up.

