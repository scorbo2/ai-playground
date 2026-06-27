# Easy Java test

The `ThreadSafeCounter` class in this directory contains three errors, with varying degrees of trickiness:

1. It doesn't compile (easy). Invalid syntax `System->out->println` instead of using dots.
2. Javadocs don't match the code (easy-ish). The `setCounter` method javadocs say that the supplied value has to be between 0 and 10, but the code insists that it should be between 5 and 8. This is a classic case of "someone updated the code but forgot to update the Javadocs" (or vice versa!).
3. Thread-unsafe (moderately difficult?). The `incrementCounterAtomically` method uses the `++` operator, which is not thread-safe in Java. Two possible solutions here: either mark the method as `synchronized`, or switch from a plain `int` to an `AtomicInteger`. Either solution is fine.

The goal is to let the LLM inspect the code with a minimal prompt, like "This code doesn't compile. Can you find and fix the problem(s) with it?", and see how thorough the LLM is when reviewing code.

## Expectations

1. Bug 1 is an easy fix.
2. Bug 2 is ambiguous - it could be a code problem, or a javadoc problem, or both. A fix is technically not possible without more context. The LLM should flag this for human attention instead of assuming one solution.
3. Bug 3 is somewhat obvious. The class javadocs brag about the code being thread-safe (it isn't), the `int` is marked as `volatile` but is used with a non-volatile `++` operator, and the method name even includes the description `Atomically`. These are huge yellow flags that should draw the LLM's attention to this. It should arrive at either of the two solutions suggested above.

This test is a bit on the easy side, but it's a good starting point and baseline for more advanced tests.
