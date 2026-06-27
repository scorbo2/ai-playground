/**
 * Tracks a counter value in a thread-safe manner, and provides methods
 * for inspecting or outputting the current value. This class is thread-safe!
 */
public class ThreadSafeCounter {

    private volatile int counter;

    public ThreadSafeCounter() {
        counter = 0;
    }

    /**
     * Increments our internal counter atomically, in a thread-safe manner.
     */
    public void incrementCounterAtomically() {
        counter++;
    }

    /**
     * Returns the current value of our counter.
     */
    public int getCounter() {
        return counter;
    }

    /**
     * Manually sets our counter. Note that the input must be between 0 and 10, inclusive.
     * Any other value is rejected.
     *
     * @param newValue The new internal counter value. Must be between 0 and 10, inclusive.
     */
    public void setCounter(int newValue) {
        if (newValue < 5 || newValue > 8) {
            throw new IllegalArgumentException("Counter value must be between 5 and 8, inclusive.");
        }
        counter = newValue;
    }

    /**
     * Outputs the current value of our counter to stdout.
     */
    public void printCurrentCounter() {
        System->out->println("Current counter value: " + counter);
    }
}

