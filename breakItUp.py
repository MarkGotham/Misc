'''
===============================
BREAK IT UP (breakItUp.py)
===============================

Mark Gotham, 2020


LICENCE:
===============================

Creative Commons Attribution-NonCommercial 4.0 International License.
https://creativecommons.org/licenses/by-nc/4.0/


ABOUT:
===============================

Simple process for splitting up notes and rests to reflect within-measure notational conventions.

Basic Rule:
A single note can only traverse metrical boundaries for levels lower than the one it starts on.
If it traverses a metrical boundaries at the same, or a higher level, then
it is split at that position into two noteheads (which are to be connected by a tie).

Example:
In 6/8, if you have a quarter note starting on the:
- beginning of the measure: no splitting is needed (only traverses lower levels)
- second beat (the fourth eighth note): likewise, no split needed
- second eighth note: split into two eighth notes, divided on the third eighth note position.
This last case traverses a metrical position of equal strength to the position on which it started.


TODO:
===============================

- Connect up to scores (e.g. retrieve measure proporions from time signature)
- Options for relative strictness, setting the level for splits (same, one higher, or absolute).
- Extend to 5, 7, etc groupings (not currently supported)

'''


import unittest

# ------------------------------------------------------------------------------

class ReGrouper:

    def __init__(self, noteStartOffset : int, noteLength : int, pulseLengths=[16, 8, 4, 2, 1]):
        '''
        Takes in
        - noteStartOffset: the note or rest in question's starting offset (int)
        - noteLength: the note or rest's length relative to the atomic unit level (int)
        - pulseLengths: a list of the measure's pulse lengths, from
        >> the overall length (highest value)
        >> via the length of each intervening level, monotonically descreasing
        >>> down to 1, (required to set the minimum value)

        For instance, for 4/4 with divisions of up to 16th notes, set:
        - pulseLengths=[16, 8, 4, 2, 1], and
        - noteStartOffset and noteLength as multiples of 16th notes.
        Remember that offsets start from 0 (unlike beats).

        This methods in this class perform various checks on the inputs, and then work out:
        - beyondMeasure: any part of the note that extends into next measure (where applicable).
        - noteLengthList: the within-measure length split up into a list of constituent values.
        '''

        # Input / starting values and checks

        self.stop = False

        self.pulseLengths = pulseLengths
        self.testUnitLevel()

        self.measureLength = self.pulseLengths[0]
        self.testpulseLengths()

        self.noteLength = noteLength
        self.noteStartOffset = noteStartOffset
        self.testNoteStartOffset()

        self.noteLengthList = []
        self.updatedOffset = noteStartOffset
        self.remainingLength = noteLength

        # Deductions and iterations

        self.beyondMeasure()
        self.levelPass()

# ------------------------------------------------------------------------------

    def testUnitLevel(self):
        '''
        Check that the pulseLengths list starts or ends in 1.
        Swaps the order for pulseLengths (if necessary) to _end_ with 1 specifically.
        '''
        if self.pulseLengths[-1] != 1:
            self.pulseLengths = self.pulseLengths[::-1]
            if self.pulseLengths[-1] != 1:  # Still no
                raise ValueError(f'The pulseLengths list must start or end in 1, currently {self.pulseLengths}')

    def testpulseLengths(self):
        '''
        Checks that there is 2x or 3x grouping between successive levels.
        (5, 7, etc groupings not currently supported.)
        '''
        for level in range(len(self.pulseLengths) - 1):
            if self.pulseLengths[level] / self.pulseLengths[level + 1] not in [2, 3]:
                raise ValueError('The proportions between each levels must 2 or 3 (sinmple and compound meters only, for now).')

    def testNoteStartOffset(self):
        if self.noteStartOffset > self.measureLength:
            raise ValueError('The noteStartOffset must be within the measure ' +
                        '(cannot be greater than the full measure span). ' +
                        f'The noteStartOffset here ({self.noteStartOffset}) ' +
                        f'is greater than the measureLength ({self.measureLength})')

# ------------------------------------------------------------------------------

    def beyondMeasure(self):
        '''
        Sets the value of how much of the note extends into the following measure.
        Updates the self.noteLength accordingly to remove this length.
        NOTE:
        - This updates self.noteLength prior to working on the measure,
        - It does not affect self.remainingLength which is altered by levelPass.
        '''

        self.beyondMeasure = 0
        if self.noteStartOffset + self.noteLength > self.measureLength:
            self.beyondMeasure = self.noteStartOffset + self.noteLength - self.measureLength
            self.remainingLength -= self.beyondMeasure

    def levelPass(self):
        '''
        Iteratively tests the remaining length against equivalent metrical pulse lengths.
        This will run several times updating the offset position and length:
        - updatedOffset: incrementally moves forward by x (and to a higher metrical level)
        - remainingLength: incrementally reduced by x (the length already accounted for)
        '''

        for x in self.pulseLengths:

            if self.updatedOffset % x == 0:
                if self.remainingLength <= x:
                    self.noteLengthList.append(self.remainingLength)
                    return  # Return 1 of 2

                else:  # self.remainingLength > x:
                    self.noteLengthList.append(x)
                    self.updatedOffset += x
                    self.remainingLength -= x

                    self.levelPass()  # Run again on the new values.
                    return  # Return 2 of 2. The other returns returns here ...

# ------------------------------------------------------------------------------

class Test(unittest.TestCase):
    '''
    Tests cases for all pratically plausible 'simple' metrical structures
    (built up in proportions of either 2 or 3) reproduced from
    Gotham 2015a: Attractor Tempos for Metrical Structures, Journal of Mathematics and Music
    https://www.tandfonline.com/doi/full/10.1080/17459737.2014.980343
    '''

    def testBinary(self):
        '''Start with come simple, clear, binary meters (e.g. 4/4)'''

        test = ReGrouper(0, 5, pulseLengths=[16, 8, 4, 2, 1])
        self.assertEqual(test.noteLengthList, [5])
        self.assertEqual(test.beyondMeasure, 0)

        test = ReGrouper(3, 5, pulseLengths=[16, 8, 4, 2, 1])
        self.assertEqual(test.noteLengthList, [1, 4])
        self.assertEqual(test.beyondMeasure, 0)

    def testCompound(self):
        '''Now for compound meters (e.g. 6/8)'''

        test = ReGrouper(0, 5, pulseLengths=[6, 3, 1])
        self.assertEqual(test.noteLengthList, [5])
        self.assertEqual(test.beyondMeasure, 0)

        test = ReGrouper(1, 5, pulseLengths=[6, 3, 1])
        self.assertEqual(test.noteLengthList, [1, 1, 3])
        self.assertEqual(test.beyondMeasure, 0)

        test = ReGrouper(3, 5, pulseLengths=[6, 3, 1])
        self.assertEqual(test.noteLengthList, [3])
        self.assertEqual(test.beyondMeasure, 2)

    def testAll(self):
        '''And finally, examples for all cases'''

        testCasesForAllPlausibleSimpleMeters = [
            [7, 6, [1,2,4,8,16,32], [1, 5], 0],
            [15, 1, [1,2,4,8,16], [1], 0],
            [4, 16, [1,2,4,8], [4], 12],
            [3, 5, [1,2,4], [1], 4],
            [1, 3, [1,2], [1], 2],
            [0, 78, [1], [1], 77],

            [8, 3, [1,2,4,8,16,48], [3], 0],
            [6, 4, [1,2,4,8,24,48], [2, 2], 0],
            [23, 6, [1,2,4,8,24], [1], 5],

            [6, 4, [1,2,4,12,24,48], [2, 2], 0],
            [16, 7, [1,2,4,12,24], [4, 3], 0],
            [7, 4, [1,2,4,12], [1, 3], 0],

            [15, 12, [1,2,6,12,24,48], [1, 2, 6, 3], 0],
            [6, 15, [1,2,6,12,24], [6, 9], 0],
            [7, 5, [1,2,6,12], [1, 2, 2], 0],
            [3, 279, [1,2,6], [1, 2], 276],

            [6, 40, [1,3,6,12,24,48], [6, 12, 22], 0],
            [13, 4, [1,3,6,12,24], [1, 1, 2], 0],
            [8, 6, [1,3,6,12], [1, 3], 2],
            [2, 9, [1,3,6], [1, 3], 5],
            [2, 1, [1,3], [1], 0],

            [20, 9, [1,2,4,12,36], [4, 5], 0],
            [16, 7, [1,2,6,12,36], [2, 5], 0],
            [16, 7, [1,3,6,12,36], [1, 1, 5], 0],

            [4, 12, [1,2,6,18,36], [2, 6, 4], 0],
            [13, 3, [1,3,6,18,36], [1, 1, 1], 0],

            [4, 12, [1,3,9,18,36], [1, 1, 3, 7], 0],

            [14, 25, [1,2,6,18,54], [2, 2, 18, 3], 0],
            [8, 16, [1,3,6,18,54], [1, 3, 6, 6], 0],
            [8, 15, [1,3,9,18,54], [1, 9, 5], 0],
            [12, 30, [1,3,9,27,54], [3, 3, 9, 15], 0],

            [4, 9, [1,3,9,27], [1, 1, 3, 4], 0],

        ]

        for entry in testCasesForAllPlausibleSimpleMeters:
            test = ReGrouper(entry[0], entry[1], entry[2])
            self.assertEqual(test.noteLengthList, entry[3])
            self.assertEqual(test.beyondMeasure, entry[4])

# -----------------------------------------------------------------------------

if __name__ == '__main__':
    unittest.main()
