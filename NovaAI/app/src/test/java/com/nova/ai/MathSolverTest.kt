package com.nova.ai

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class MathSolverTest {

    @Test
    fun binaryOps() {
        assertEquals("7 plus 5 is twelve.", MathSolver.trySolve("what is 7 plus 5"))
        assertEquals("100 plus 50 is 150.", MathSolver.trySolve("what is 100 plus 50"))
        assertEquals("15 minus 8 is seven.", MathSolver.trySolve("15 minus 8"))
        assertEquals("9 times 9 is 81.", MathSolver.trySolve("what is 9 times 9"))
        assertEquals("81 divided by 9 is nine.", MathSolver.trySolve("what is 81 divided by 9"))
        assertEquals("12 divided by 5 is 2.4.", MathSolver.trySolve("12 / 5"))
        assertEquals("you can not divide by zero.", MathSolver.trySolve("10 divided by 0"))
    }

    @Test
    fun wordNumbersAndExtras() {
        assertEquals("3 plus 4 is seven.", MathSolver.trySolve("what is three plus four"))
        assertEquals("double 7 is fourteen.", MathSolver.trySolve("double 7"))
        assertEquals("half of 20 is ten.", MathSolver.trySolve("half of 20"))
        assertEquals("11 squared is 121.", MathSolver.trySolve("11 squared"))
    }

    @Test
    fun nonMathStaysNull() {
        assertNull(MathSolver.trySolve("tell me a joke"))
        assertNull(MathSolver.trySolve("what is the capital of france"))
        assertNull(MathSolver.trySolve("hello"))
    }
}
