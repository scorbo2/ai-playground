# Timings and context usage for implementation

- Dev stage 1 (model 1): 27:19 (+2:44 for one bug fix): 80K context used
- Dev stage 2 (model 1): Failed! Couldn't figure out pygame_gui.
- Dev stage 2 (model 2): 44:06: 71K context used, compacted but finished the stage
- Dev stage 3 (model 3): 19:56: 64K context used
- Dev stage 4 (model 3): 22:40: 105K context used (same session)
- Dev stage 5 (model 3): 17:41: 69K context used
- Dev stage 6 (model 3): 38:15: 148K+ context used (same session, compaction)

== Compliance check! Model 1 finds 9 defects in 18:48, 94K context ==

== Model 3 fixes these in a new session in 41:38, 148K+ context, compaction ==

- Dev stage 7 (model 3): 40:43, 115K context used
- Dev stage 8 (model 3): 31:35, 116K context used, compaction
- Dev stage 9 (model 2, because it's a hard one): 2:02:52 (compaction 2x)

== Compliance check! Model 1 finds 3 defects in 19:40, 98K context ==

== Model 3 fixes these in a new session in 18:11, 90K context ==

- Dev stage 10 (model 3): 37:42, 148K+ context used (compaction 1x)
- Dev stage 11 (model 3): 28:11, 148K+ context used (compaction 1x)
- Dev stage 12 (model 3): 34:52, 148K+ context used (compaction 1x)
- Dev stage 13 (model 3): 29:51, 148K+ context used (compaction 1x)
- Dev stage 14 (model 3): 8:27, 56K context used

== CODE FROZEN! No changes after this point! ==

Code review by Qwen 3.8 Flash Next: 14:49, 300K+ context used (compaction 1x!)

## Model identities

To be filled in later! Can you guess?

- **Model 1**: the smallest model with the largest context
- **Model 2**: the largest model with the smallest context
- **Model 3**: the medium model that did 80% of the work

