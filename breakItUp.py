"""
===============================
BREAK IT UP (breakItUp.py)
===============================

Mark Gotham, 2020-21


LICENCE:
===============================

Creative Commons Attribution-ShareAlike 4.0 International License
https://creativecommons.org/licenses/by-sa/4.0/


ABOUT:
===============================

Split up notes and rests to reflect the
within-measure notational conventions
of metrical hierarchies in Western classical music.

This functionality picks up from previous discussions on the music21
list (https://groups.google.com/g/music21list/c/5G-UafJeW94/m/YcEBE0PFAQAJ)
and repo (issue 992, https://github.com/cuthbertLab/music21/issues/992).

Basically, the idea is that
a single note can only cross metrical boundaries
for levels lower than the one it starts on.
If it traverses a metrical boundaries at a higher level, then
it is split at that position into two note-heads to be connected by a tie.

For notes on how that is realised here,
and on the many variant options supported, see the docs for 'ReGrouper'.


TODO:
===============================

For full integration with music21, this will need:

1. new / modified functionality within music21 that reliably returns
every metrical level for any meter.
The subdivideNestedHierarchy routine is close, but not currently there.
Local routines handle this here.

2. to connect up to scores (work with note and time signature by context).

"""

from typing import Union, Optional
import numpy as np  # note optional - not part of prospective music21 integration
import unittest


# ------------------------------------------------------------------------------

class ReGrouper:
    """
    Split up notes and rests to reflect the
    within-measure notational conventions
    of metrical hierarchies in Western classical music.

    This class
    takes in a note (expressed in terms of the offset position and duration),
    and metrical context (the overall structure, and which part to use), and
    returns a list of offset-duration pairs for the broken-up note value.

    The basic premise here is that a single note can only traverse metrical boundaries
    for levels lower than the one it starts on.
    If it traverses the metrical boundary of a higher level, then
    it is split at that position into two note-heads to be connected by a tie.

    There are many variants on this basic set up.
    This class aims to support almost any such variant, while providing easy defaults
    for simple, standard practice.

    The flexibility comes from the definition of a metrical structure.
    Here, everything ultimately runs through a single representation
    of metrical levels in terms of offsets expressed by quarter length
    from the start of the measure,
    e.g. levels 0-3 of a time signature like 4/4 would be represented as:
    [[0.0, 4.0],
    [0.0, 2.0, 4.0],
    [0.0, 1.0, 2.0, 3.0, 4.0],
    [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]]

    Each split of the note duration serves to move up one metrical level.
    For instance, for the 4/4 example above, a note of duration 2.0 starting at offset
    0.25 connects to 0.5 in level 3 (duration = 0.25), then
    0.5 connects to 1.0 in level 2 (duration = 0.5), then
    1.0 connects to 2.0 in level 1 (duration = 1.0), and
    this leaves a duration of 0.25 to start on offset 2.0.
    The data is returned as a list of (position, duration) tuples.
    The values for the example would be:
    [(0.25, 0.25),
    (0.5, 0.5),
    (1.0, 1.0),
    (1.0, 0.25)].

    There are three main user options (for advanced use cases only):
    tweak a metrical hierarchy to only consider certain levels (see the 'levels' parameter);
    define a metrical structure completely from scratch ('offsetHierarchy');
    determine the handling of splits within a level for metres like 6/8 ('splitSameLevel').

    The input parameters are:

    noteStartOffset:
    the note or rest in question's starting offset.

    noteLength:
    the note or rest's length.

    timeSignature (optional):
    the time signature (currently expressed as a string).
    to be converted into an offsetHierarchy.

    levels (optional):
    the default arrangement is to use all levels of a time signature's metrical hierarchy.
    Alternatively, this parameter allows users to select certain levels for in-/exclusion.
    See the offsetsFromTSAndLevels fucntion for further explanation.

    pulseLengths (optional):
    this provides an alternative way of expressing the metrical hierarchy
    in terms of pulse lengths (by quarter length), again
    to be converted into an offsetHierarchy.
    See offsetListFromPulseLengths for further explanation.

    offsetHierarchy (optional):
    a final alternative way of expressing the metrical hierarchy
    completely from scratch (ignoring all other parameters and defaults).
    Use this for advanced cases requiring non-standard metrical structures
    including those without 2-/3- grouping, or even nested hierarchies.

    splitSameLevel:
    in cases of metrical structures with a 3-grouping
    (i.e. two 'weak' events between a 'strong' in compound signatures like 6/8)
    some conventions chose to split notes within-level as well as between them.
    For instance, with a quarter note starting on the second eighth note (offset 0.5) of 6/8,
    some will want to split that into two 1/8th notes, divided on the third eighth note position,
    while others will want to leave this intact.
    The splitSameLevel option accommodates this:
    it effects the within-level split when set to True and not otherwise (default).

    At least one of
    timeSignature,
    levels (with a timeSignature),
    pulseLengths, or
    offsetHierarchy
    must be specified.

    These are listed in order from the most standard to the most specialised.
    The timeSignature defaults will serve most use cases, and the
    'levels' parameter should be enough for a particular editorial style.
    """

    def __init__(self,
                 noteStartOffset: Union[int, float],
                 noteLength: Union[int, float],
                 timeSignature: Optional[str] = None,
                 levels: Optional[list] = None,
                 pulseLengths: Optional[list] = None,
                 offsetHierarchy: Optional[list] = None,
                 splitSameLevel: bool = False):

        # Retrieve or create the metrical structure
        if offsetHierarchy:
            self.offsetHierarchy = offsetHierarchy
        elif pulseLengths:
            self.offsetHierarchy = offsetListFromPulseLengths(pulseLengths,
                                                              require2or3betweenLevels=False)
        elif levels:
            if not timeSignature:
                raise ValueError('To specify levels, please also enter a valid time signature.')
            self.offsetHierarchy = offsetsFromTSAndLevels(timeSignature, levels)
        else:  # timeSignature, not levels specified
            self.offsetHierarchy = offsetsFromTSAndLevels(timeSignature)

        if not self.offsetHierarchy:
            raise ValueError('Could not create an offsetHierarchy.'
                             'Please input a valid time signature or equivalent.')

        self.noteLength = noteLength
        self.noteStartOffset = noteStartOffset
        self.splitSameLevel = splitSameLevel

        # Initialise
        self.offsetDurationPairs = []
        self.updatedOffset = noteStartOffset
        self.remainingLength = noteLength
        self.levelPass()

    # ------------------------------------------------------------------------------

    def levelPass(self):
        """
        Having established the structure of the offsetHierarchy,
        this method iterates across the levels of that hierarchy to find
        the current offset position, and (through advanceOneStep) the offset position to map to.

        This method runs once for each such mapping,
        typically advancing up one (or more) layer of the metrical hierarchy with each call.
        'Typically' because splitSameLevel is supported where relevant.

        Each iteration creates a new offset-duration pair
        stored in the offsetDurationPairs list
        that records the constituent parts of the split note.
        """

        for levelIndex in range(len(self.offsetHierarchy)):

            if self.remainingLength <= 0:  # sic, here due to the various routes through
                return

            thisLevel = self.offsetHierarchy[levelIndex]

            if self.updatedOffset in thisLevel:
                if levelIndex == 0:  # i.e. updatedOffset == 0
                    self.offsetDurationPairs.append((self.updatedOffset,
                                                     self.remainingLength))
                    return
                else:  # level up. NB: duplicates in nested hierarchy help here
                    if self.splitSameLevel:  # relevant option for e.g. 6/8
                        self.advanceOneStep(thisLevel)
                    else:  # usually
                        self.advanceOneStep(self.offsetHierarchy[levelIndex - 1])

        if self.remainingLength > 0:  # offset not in the hierarchy at all
            self.advanceOneStep(self.offsetHierarchy[-1])  # get to lowest level
            # Now start the process with the metrical structure:
            self.levelPass()

    def advanceOneStep(self, positionsList: list):
        """
        For an offset position, and a metrical level expressed as a list of offsets,
        finds the next higher value from those levels.
        Used for determining iterative divisions.
        """
        for p in positionsList:
            if p > self.updatedOffset:
                durationToNextPosition = p - self.updatedOffset
                if self.remainingLength <= durationToNextPosition:
                    self.offsetDurationPairs.append((self.updatedOffset,
                                                     self.remainingLength))
                    # done but still reduce remainingLength to end the whole process in levelPass
                    self.remainingLength -= durationToNextPosition
                    return
                else:  # self.remainingLength > durationToNextPosition:
                    self.offsetDurationPairs.append((self.updatedOffset,
                                                     durationToNextPosition))
                    # Updated offset and position; run again
                    self.updatedOffset = p
                    self.remainingLength -= durationToNextPosition
                    self.levelPass()  # NB: to re-start from top as may have jumped a level
                    return


# ------------------------------------------------------------------------------

def offsetHierarchyFromTS(tsStr: str, minimumPulse: int = 64):
    """
    Create an offset hierarchy for almost any time signature
    directly from a string (e.g. '4/4') without dependencies.
    Returns a list of lists with offset positions by level.
    
    For instance:    

    >>> offsetHierarchyFromTS('4/4')  # note the half cycle division
    [[0.0, 4.0],
    [0.0, 2.0, 4.0],
    [0.0, 1.0, 2.0, 3.0, 4.0],
    [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0],
    ...
    
    >>> offsetHierarchyFromTS('6/8')  # note the macro-beat division
    [[0.0, 3.0],
    [0.0, 1.5, 3.0],
    [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0],
    ...
    
    Numerators like 5 and 7 are supported.
    Use the total value only to avoid segmentation about the denominator level:
    >>> offsetHierarchyFromTS('5/4')  # note no 2+3 or 3+2 level division
    [[0.0, 5.0],
    [0.0, 1.0, 2.0, 3.0, 4.0, 5.0],
    ... 

    Or use numerator addition in the form 'X+Y/Z' to clarify this level ...
    
    >>> offsetHierarchyFromTS('2+3/4')  # note the 2+3 division
    [[0.0, 5.0],
    [0.0, 2.0, 5.0],
    [0.0, 1.0, 2.0, 3.0, 4.0, 5.0],
    ...

    >>> offsetHierarchyFromTS('2+2+3/8')  # note the 2+2+3 division
    [[0.0, 4.5],
    [0.0, 1.0, 2.0, 4.5],
    [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.5],
    ... 
    
    >>> offsetHierarchyFromTS('2+2+2+3/8')  # note the 2+2+2+3 division
    [[0.0, 4.5],
    [0.0, 1.0, 2.0, 3.0, 4.5],
    [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5],
    ... 
        
    Only standard denominators are supported:
    i.e. time signatures in the form X/ one of
    1, 2, 4, 8, 16, 32, or 64.
    No so-called 'irrational' meters yet (e.g. 2/3), sorry!
    
    Likewise the minimumPulse must be set to one of these values 
    (default = 64 for 64th note) and not be longer than the meter.
    
    TODO:
    Whole signatures added together in the form 'P/Q+R/S' 
    (split by '+' before '/').
    """

    # Prep and checks
    numerator, denominator = tsStr.split('/')
    numerators = [int(x) for x in numerator.split('+')]
    denominator = int(denominator)
    # TODO if more than one '/' (e.g. 4/4 + 3/8) then split by + first

    supportedDenominators = [1, 2, 4, 8, 16, 32, 64]
    if denominator not in supportedDenominators:
        raise ValueError("Invalid time signature denominator; chose from one of:"
                         f" {supportedDenominators}.")
    if minimumPulse not in supportedDenominators:
        raise ValueError(
            "Invalid minimumPulse: it should be expressed as a note value, from one of"
            f" {supportedDenominators}.")

    # Prep. 'hiddenLayer'/s
    hiddenLayerMappings = (
        ([4], [2, 2]),
        ([6], [3, 3]),
        ([9], [3, 3, 3]),  # alternative groupings need to be set out, e.g. 2+2+2+3 
        ([12], [[6, 6], [3, 3, 3, 3]]),  # " e.g. 2+2+2+3 
        ([15], [3, 3, 3, 3, 3]),  # " e.g. 2+2+2+3 
        ([6, 9], [[6, 9], [3, 3, 3, 3, 3]]),  # TODO generalise
        ([9, 6], [[6, 6], [3, 3, 3, 3, 3]]),
    )

    for h in hiddenLayerMappings:
        if numerators == h[0]:
            numerators = h[1]

    if type(numerators[0]) == list:
        sumNum = sum(numerators[0])
    else:
        sumNum = sum(numerators)

    measureLength = sumNum * 4 / denominator

    # Now ready for each layer in order: 

    # 1. top level = whole cycle (always included as entry[0])
    offsetHierarchy = [[0.0, measureLength]]

    # 2. 'hidden' layer/s
    if len(numerators) > 1:  # whole cycle covered.
        if type(numerators[0]) == list:
            for level in numerators:
                offsets = offsetsFromBeatPattern(level, denominator)
                offsetHierarchy.append(offsets)
        else:
            offsets = offsetsFromBeatPattern(numerators, denominator)
            offsetHierarchy.append(offsets)

    # 3. Finally, everything at the denominator level and shorter:
    thisDenominatorPower = supportedDenominators.index(denominator)
    maxDenominatorPower = supportedDenominators.index(minimumPulse)

    for thisDenominator in supportedDenominators[thisDenominatorPower:maxDenominatorPower + 1]:
        thisQL = 4 / thisDenominator
        offsets = offsetsFromLengths(measureLength, thisQL)
        offsetHierarchy.append(offsets)

    return offsetHierarchy


def offsetsFromTSAndLevels(timeSigStr: str,  # Union[str, meter.timeSignature]
                           levels: list = [0, 1, 2, 3],
                           useMusic21: bool = False):
    """
    Gets offsets from a time signature and a list of levels.
    Records the offsets associated with each level as a list,
    and return a list of those lists.

    Levels are defined by the hierarchies recorded in the time signature.
    The 0th level for the full cycle (offset 0.0 and full measure length) is always included.
    '1' stands for the 1st level below that of the full metrical cycle
    (e.g. a half cycle of 4/4 and similar time signtures like 2/2).
    '2' is the next level down, (quarter cycle) and so on.

    The functions arranges the list of levels in increasing order:
    level 0 is always included, and
    the maximum permitted level (depth) is 6.

    Level choices do not need to be successive:
    e.g. in 4/4 a user could choose [1, 3],
    with 1 standing for the half note level,
    3 for the eight note level,
    and skipping in intervening level 2 (quarter note).

    IMPORTANT:
    the music21 routines involved (meter.MeterSequence.subdivideNestedHierarchy)
    currently only work realibly for cases like 4/4.
    We need to fix even 6/8 before integrating this function.
    Currently 'useMusic21' is an parameter, default = False.

    For, instance, 4/4 recognises the levels corresponding to whole, half, quarter notes etc
    >>> offsetsFromTSAndLevels('4/4', [1, 2, 3], useMusic21=True)
    [[0.0], [0.0, 2.0], [0.0, 1.0, 2.0, 3.0], [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5]]

    But 6/8 skips straight from the meter to the 1/8 note without the half-measure (compound) beat.
    >>> offsetsFromTSAndLevels('6/8', [1, 2], useMusic21=True)
    [[0.0], [0.0, 0.5, 1.0, 1.5, 2.0, 2.5],
    [0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 2.75]]

    This function provides a hard-coded workaround that's called when useMusic21=False (default).
    Note also the inclusion of the full cycle length here (useful in ReGrouper).
    >>> offsetsFromTSAndLevels('6/8', [1, 2], useMusic21=False)
    [[0.0, 3.0], [0.0, 1.5, 3.0], [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0]]

    The music21 beamSequence method may also be useful here (i.e. integrating the two).
    See discussion on music21, issue 992.
    """

    if max(levels) > 6:
        raise ValueError('6 is the maximum level depth supported.')
    levels = sorted(levels)  # smallest first
    if 0 not in levels:  # likely, and not a problem
        levels = [0] + levels  # Always have level 0 as first entry

    offsetsByLevel = []

    if useMusic21:
        from music21 import meter
        ms = meter.MeterSequence(timeSigStr)
        ms.subdivideNestedHierarchy(max(levels))
        for level in levels:
            offsetsThisLevel = [x[0] for x in ms.getLevelSpan(level)]
            offsetsByLevel.append(offsetsThisLevel)
    else:
        fullHierarchy = offsetHierarchyFromTS(timeSigStr)
        for level in levels:
            offsetsByLevel.append(fullHierarchy[level])

    return offsetsByLevel


def offsetListFromPulseLengths(pulseLengths: list,
                               measureLength: Union[float, int, None] = None,
                               require2or3betweenLevels: bool = False):
    """
    Convert a list of pulse lengths into a corresponding list of offset positions.
    All values (pulse lengths, offset positions, and measureLength) 
    are all expressed in terms of quarter length.
    
    The measureLength is not required - if not provided it's taken to be the longest pulse length.

    >>> offsetListFromPulseLengths(pulseLengths=[4, 2, 1, 0.5])
    [[0.0, 4.0],
    [0.0, 2.0, 4.0],
    [0.0, 1.0, 2.0, 3.0, 4.0],
    [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]]

    This doesn't work for ('nonisochronous') pulse streams of varying duration
    in time signatures like 5/x, 7/x
    (e.g. the level of 5/4 with dotted/undotted 1/2 notes).

    It is still perfectly fine to use this for the
    regular, equally spaced ('isochronous') pulse streams of those meters
    (e.g. the 1/4 note level of 5/4).

    The list of pulse lengths is set in decreasing order.

    If require2or3betweenLevels if True (default), this functions checks that
    each level is either a 2 or 3 multiple of the next.

    By default, the measureLength is taken by the longest pulse length.
    Alternatively, this can be user-defined to anything that is
    longer than the longest pulse and
    (if require2or3betweenLevels is True) then
    exactly 2x or 3x longer.
    """

    pulseLengths = sorted(pulseLengths)[::-1]  # largest number first

    if not measureLength:
        measureLength = pulseLengths[0]

    else:
        if pulseLengths[0] > measureLength:
            raise ValueError('Pulse lengths cannot be longer than the measureLength.')

    if require2or3betweenLevels:
        for level in range(len(pulseLengths) - 1):
            if pulseLengths[level] / pulseLengths[level + 1] not in [2, 3]:
                raise ValueError('The proportion between consecutive levels is not 2 or 3 in '
                                 f'this case: {pulseLengths[level]}:{pulseLengths[level + 1]}.')

    offsetList = []

    for pulseLength in pulseLengths:
        offsets = offsetsFromLengths(measureLength, pulseLength)
        offsetList.append(offsets)

    return offsetList


# ------------------------------------------------------------------------------

# Subsidiary one-level converters

def offsetsFromLengths(measureLength: Union[float, int],
                       pulseLength: Union[float, int],
                       includeMeasureLength: bool = True,
                       useNumpy: bool = True):
    """
    Convert a pulse length and measure length into a list of offsets.
    All expressed in quarter length.
    If includeMeasureLength is True (default) then each level ends with the full cycle length
    (i.e. the offset of the start of the next cycle).
    """
    if useNumpy:
        offsets = [i for i in np.arange(0, measureLength, pulseLength)]
    else:  # music21 avoids numpy right?
        currentIndex = 0
        offsets = []
        while currentIndex < measureLength:
            offsets.append(currentIndex)
            currentIndex += pulseLength

    if includeMeasureLength:
        return offsets + [measureLength]
    else:
        return offsets


def offsetsFromBeatPattern(beatList: list,
                           denominator: Union[float, int],
                           includeMeasureLength: bool = True):
    """
    Converts a list of beats 
    like [2, 2, 2]
    or [3, 3]
    or indeed
    [6, 9]
    into a list of offsets.
    """
    offsets = []
    count = 0
    for x in beatList:
        thisOffset = count * 4 / denominator
        offsets.append(thisOffset)
        count += x
    if includeMeasureLength:  # include last value
        thisOffset = count * 4 / denominator
        offsets.append(thisOffset)
    return offsets


# ------------------------------------------------------------------------------

# Examples of the offset hierarchy structures we're aiming for.
# For reference and testing.
# Down to 1/32 note level [0, 0.125 ... ] in each case

offsetHierarchyExamples = {

    '2/2': [[0.0, 4.0],
            [0.0, 2.0, 4.0],
            [0.0, 1.0, 2.0, 3.0, 4.0],
            [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0],
            [0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75,
             2.0, 2.25, 2.5, 2.75, 3.0, 3.25, 3.5, 3.75, 4.0],
            [0.0, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875,
             1.0, 1.125, 1.25, 1.375, 1.5, 1.625, 1.75, 1.875,
             2.0, 2.125, 2.25, 2.375, 2.5, 2.625, 2.75, 2.875,
             3.0, 3.125, 3.25, 3.375, 3.5, 3.625, 3.75, 3.875, 4.0]],

    '3/2': [[0.0, 6.0],
            [0.0, 2.0, 4.0, 6.0],
            [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
            [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0],
            [0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 2.75, 3.0, 3.25, 3.5, 3.75,
             4.0, 4.25, 4.5, 4.75, 5.0, 5.25, 5.5, 5.75, 6.0],
            [0.0, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875,
             1.0, 1.125, 1.25, 1.375, 1.5, 1.625, 1.75, 1.875,
             2.0, 2.125, 2.25, 2.375, 2.5, 2.625, 2.75, 2.875,
             3.0, 3.125, 3.25, 3.375, 3.5, 3.625, 3.75, 3.875,
             4.0, 4.125, 4.25, 4.375, 4.5, 4.625, 4.75, 4.875,
             5.0, 5.125, 5.25, 5.375, 5.5, 5.625, 5.75, 5.875, 6.0]],

    '4/2': [[0.0, 8.0],
            [0.0, 4.0, 8.0],
            [0.0, 2.0, 4.0, 6.0, 8.0],
            [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0],
            [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0, 7.5, 8.0],
            [0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 2.75,
             3.0, 3.25, 3.5, 3.75, 4.0, 4.25, 4.5, 4.75, 5.0, 5.25, 5.5, 5.75,
             6.0, 6.25, 6.5, 6.75, 7.0, 7.25, 7.5, 7.75, 8.0],
            [0.0, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875,
             1.0, 1.125, 1.25, 1.375, 1.5, 1.625, 1.75, 1.875,
             2.0, 2.125, 2.25, 2.375, 2.5, 2.625, 2.75, 2.875,
             3.0, 3.125, 3.25, 3.375, 3.5, 3.625, 3.75, 3.875,
             4.0, 4.125, 4.25, 4.375, 4.5, 4.625, 4.75, 4.875,
             5.0, 5.125, 5.25, 5.375, 5.5, 5.625, 5.75, 5.875,
             6.0, 6.125, 6.25, 6.375, 6.5, 6.625, 6.75, 6.875,
             7.0, 7.125, 7.25, 7.375, 7.5, 7.625, 7.75, 7.875, 8.0]],

    '2/4': [[0.0, 2.0],
            [0.0, 1.0, 2.0],
            [0.0, 0.5, 1.0, 1.5, 2.0],
            [0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0],
            [0.0, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875,
             1.0, 1.125, 1.25, 1.375, 1.5, 1.625, 1.75, 1.875, 2.0]],

    '3/4': [[0.0, 3.0],
            [0.0, 1.0, 2.0, 3.0],
            [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0],
            [0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 2.75, 3.0],
            [0.0, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875,
             1.0, 1.125, 1.25, 1.375, 1.5, 1.625, 1.75, 1.875,
             2.0, 2.125, 2.25, 2.375, 2.5, 2.625, 2.75, 2.875, 3.0]],

    '4/4': [[0.0, 4.0],
            [0.0, 2.0, 4.0],
            [0.0, 1.0, 2.0, 3.0, 4.0],
            [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0],
            [0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75,
             2.0, 2.25, 2.5, 2.75, 3.0, 3.25, 3.5, 3.75, 4.0],
            [0.0, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875,
             1.0, 1.125, 1.25, 1.375, 1.5, 1.625, 1.75, 1.875,
             2.0, 2.125, 2.25, 2.375, 2.5, 2.625, 2.75, 2.875,
             3.0, 3.125, 3.25, 3.375, 3.5, 3.625, 3.75, 3.875, 4.0]],

    '6/8': [[0.0, 3.0],
            [0.0, 1.5, 3.0],  # music21 issues with this level
            [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0],
            [0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 2.75, 3.0],
            [0.0, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875, 1.0, 1.125, 1.25, 1.375,
             1.5, 1.625, 1.75, 1.875, 2.0, 2.125, 2.25, 2.375, 2.5, 2.625, 2.75, 2.875, 3.0]],

    '9/8': [[0.0, 4.5],
            [0.0, 1.5, 3.0, 4.5],  # music21 issues with this level
            [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5],
            [0.0, 0.25, 0.5, 0.75, 1.0, 1.25,
             1.5, 1.75, 2.0, 2.25, 2.5, 2.75,
             3.0, 3.25, 3.5, 3.75, 4.0, 4.25, 4.5],
            [0.0, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875, 1.0, 1.125, 1.25, 1.375,
             1.5, 1.625, 1.75, 1.875, 2.0, 2.125, 2.25, 2.375, 2.5, 2.625, 2.75, 2.875,
             3.0, 3.125, 3.25, 3.375, 3.5, 3.625, 3.75, 3.875, 4.0, 4.125, 4.25, 4.375, 4.5]],

    '12/8': [[0.0, 6.0],
             [0.0, 3.0, 6.0],  # music21 issues with this level
             [0.0, 1.5, 3.0, 4.5, 6.0],  # music21 issues with this level
             [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0],
             [0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 2.75, 3.0, 3.25, 3.5,
              3.75, 4.0, 4.25, 4.5, 4.75, 5.0, 5.25, 5.5, 5.75, 6.0],
             [0.0, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875, 1.0, 1.125, 1.25, 1.375, 1.5, 1.625,
              1.75, 1.875, 2.0, 2.125, 2.25, 2.375, 2.5, 2.625, 2.75, 2.875, 3.0, 3.125, 3.25,
              3.375, 3.5, 3.625, 3.75, 3.875, 4.0, 4.125, 4.25, 4.375, 4.5, 4.625, 4.75, 4.875, 5.0,
              5.125, 5.25, 5.375, 5.5, 5.625, 5.75, 5.875, 6.0]],

    '2+3/4': [[0.0, 5.0],
              [0.0, 2.0, 5.0],  # music21 issues with this level
              [0.0, 1.0, 2.0, 3.0, 4.0, 5.0],
              [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0],
              [0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75,
               2.0, 2.25, 2.5, 2.75, 3.0, 3.25, 3.5, 3.75, 4.0, 4.25, 4.5, 4.75, 5.0],
              [0.0, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875,
               1.0, 1.125, 1.25, 1.375, 1.5, 1.625, 1.75, 1.875,
               2.0, 2.125, 2.25, 2.375, 2.5, 2.625, 2.75, 2.875,
               3.0, 3.125, 3.25, 3.375, 3.5, 3.625, 3.75, 3.875,
               4.0, 4.125, 4.25, 4.375, 4.5, 4.625, 4.75, 4.875, 5.0]],

    '3+2/4': [[0.0, 5.0],
              [0.0, 3.0, 5.0],  # music21 issues with this level
              [0.0, 1.0, 2.0, 3.0, 4.0, 5.0],
              [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0],
              [0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 2.75,
               3.0, 3.25, 3.5, 3.75, 4.0, 4.25, 4.5, 4.75, 5.0],
              [0.0, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875,
               1.0, 1.125, 1.25, 1.375, 1.5, 1.625, 1.75, 1.875,
               2.0, 2.125, 2.25, 2.375, 2.5, 2.625, 2.75, 2.875,
               3.0, 3.125, 3.25, 3.375, 3.5, 3.625, 3.75, 3.875,
               4.0, 4.125, 4.25, 4.375, 4.5, 4.625, 4.75, 4.875, 5.0]],

    '2+2+3/4': [[0.0, 7.0],
                [0.0, 2.0, 4.0, 7.0],  # music21 issues with this level
                [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0],
                [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0],
                [0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 2.75, 3.0, 3.25, 3.5,
                 3.75, 4.0, 4.25, 4.5, 4.75, 5.0, 5.25, 5.5, 5.75, 6.0, 6.25, 6.5, 6.75, 7.0],
                [0.0, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875,
                 1.0, 1.125, 1.25, 1.375, 1.5, 1.625, 1.75, 1.875,
                 2.0, 2.125, 2.25, 2.375, 2.5, 2.625, 2.75, 2.875,
                 3.0, 3.125, 3.25, 3.375, 3.5, 3.625, 3.75, 3.875,
                 4.0, 4.125, 4.25, 4.375, 4.5, 4.625, 4.75, 4.875,
                 5.0, 5.125, 5.25, 5.375, 5.5, 5.625, 5.75, 5.875,
                 6.0, 6.125, 6.25, 6.375, 6.5, 6.625, 6.75, 6.875, 7.0]],

    '3+2+2/4': [[0.0, 7.0],
                [0.0, 3.0, 5.0, 7.0],  # music21 issues with this level
                [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0],
                [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0],
                [0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 2.75, 3.0, 3.25, 3.5,
                 3.75, 4.0, 4.25, 4.5, 4.75, 5.0, 5.25, 5.5, 5.75, 6.0, 6.25, 6.5, 6.75, 7.0],
                [0.0, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875,
                 1.0, 1.125, 1.25, 1.375, 1.5, 1.625, 1.75, 1.875,
                 2.0, 2.125, 2.25, 2.375, 2.5, 2.625, 2.75, 2.875,
                 3.0, 3.125, 3.25, 3.375, 3.5, 3.625, 3.75, 3.875,
                 4.0, 4.125, 4.25, 4.375, 4.5, 4.625, 4.75, 4.875,
                 5.0, 5.125, 5.25, 5.375, 5.5, 5.625, 5.75, 5.875,
                 6.0, 6.125, 6.25, 6.375, 6.5, 6.625, 6.75, 6.875, 7.0]],

    '2+3+2/4': [[0.0, 7.0],
                [0.0, 2.0, 5.0, 7.0],  # music21 issues with this level
                [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0],
                [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0],
                [0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 2.75,
                 3.0, 3.25, 3.5, 3.75, 4.0, 4.25, 4.5, 4.75, 5.0, 5.25, 5.5, 5.75, 6.0, 6.25, 6.5,
                 6.75, 7.0],
                [0.0, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875,
                 1.0, 1.125, 1.25, 1.375, 1.5, 1.625, 1.75, 1.875,
                 2.0, 2.125, 2.25, 2.375, 2.5, 2.625, 2.75, 2.875,
                 3.0, 3.125, 3.25, 3.375, 3.5, 3.625, 3.75, 3.875,
                 4.0, 4.125, 4.25, 4.375, 4.5, 4.625, 4.75, 4.875,
                 5.0, 5.125, 5.25, 5.375, 5.5, 5.625, 5.75, 5.875,
                 6.0, 6.125, 6.25, 6.375, 6.5, 6.625, 6.75, 6.875, 7.0]],
}


# ------------------------------------------------------------------------------

class Test(unittest.TestCase):

    def setUp(self) -> None:

        self.testMetres = []

        for x in (
                ('4/4',
                 [1, 2],
                 [4, 2, 1],
                 [[0.0, 4.0], [0.0, 2.0, 4.0], [0.0, 1.0, 2.0, 3.0, 4.0]]
                 ),
                ('4/4',
                 [3],
                 [4, 0.5],
                 [[0.0, 4.0], [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]]
                 ),
                ('6/8',
                 [1, 2],
                 [3, 1.5, 0.5],
                 [[0.0, 3.0], [0.0, 1.5, 3.0], [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0]]
                 ),
        ):
            newDict = {'ts': x[0],
                       'levels': x[1],
                       'pulses': x[2],
                       'offsets': x[3]
                       }
            self.testMetres.append(newDict)

    def testGetOffsetsFromTSAndLevels(self):
        for tc in self.testMetres:
            t = offsetsFromTSAndLevels(tc['ts'], tc['levels'])
            self.assertEqual(t, tc['offsets'])

    def testPulseLengthsToOffsetList(self):
        for tc in self.testMetres:
            t = offsetListFromPulseLengths(pulseLengths=tc['pulses'],
                                           require2or3betweenLevels=False)
            self.assertEqual(t, tc['offsets'])

    def testRequire2or3(self):
        """
        Test a case with require2or3betweenLevels=True.
        """
        self.assertRaises(ValueError,
                          offsetListFromPulseLengths,
                          pulseLengths=[4, 1],
                          require2or3betweenLevels=True)

    def testOffsetHierarchyFromTS(self):
        """
        Test offsetHierarchyFromTS by running through all
        the offsetHierarchyExamples test cases.
        """
        for k in offsetHierarchyExamples:
            oh = offsetHierarchyFromTS(k, minimumPulse=32)
            self.assertEqual(oh, offsetHierarchyExamples[k])

    def testFromPulseLength(self):
        """
        (Reproduces the equivalent task from the previous version of this script.)
    
        Tests cases from pulse lengths for all practically plausible metrical structures
        built up in proportions of either 2 or 3. Reproduced from
        Gotham 2015a: Attractor Tempos for Metrical Structures, Journal of Mathematics and Music
        https://www.tandfonline.com/doi/full/10.1080/17459737.2014.980343
    
        That said, note that
        for convenience this test takes the unit pulse as a quarter and 
        builds everything up from there, which means
        choosing examples like 16/4 rather than 4/4 with divisions.
    
        Although this is not reflective of common time signatures,
        the metrical structures are equivalent and so this is a perfectly valid test.
        Let's call it a test of the rare signatures like 16/4.
        """

        testCasesForAllPlausibleSimpleMeters = [
            [7, 6, [1, 2, 4, 8, 16, 32], [(7, 1), (8, 5)]],
            [15, 1, [1, 2, 4, 8, 16], [(15, 1)]],
            [4, 4, [1, 2, 4, 8], [(4, 4)]],
            [1, 3, [1, 2, 4], [(1, 1), (2, 2)], 4],
            [1, 1, [1, 2], [(1, 1)], 2],
            [0, 1, [1], [(0, 1)], 77],

            [8, 3, [1, 2, 4, 8, 16, 48], [(8, 3)]],
            [6, 4, [1, 2, 4, 8, 24, 48], [(6, 2), (8, 2)]],
            [13, 6, [1, 2, 4, 8, 24], [(13, 1), (14, 2), (16, 3)]],

            [6, 4, [1, 2, 4, 12, 24, 48], [(6, 2), (8, 2)]],
            [16, 7, [1, 2, 4, 12, 24], [(16, 7)]],
            [7, 4, [1, 2, 4, 12], [(7, 1), (8, 3)]],

            [15, 12, [1, 2, 6, 12, 24, 48], [(15, 1), (16, 2), (18, 6), (24, 3)]],
            [6, 15, [1, 2, 6, 12, 24], [(6, 6), (12, 9)]],
            [7, 5, [1, 2, 6, 12], [(7, 1), (8, 4)]],
            [3, 2, [1, 2, 6], [(3, 1), (4, 1)]],

            [6, 40, [1, 3, 6, 12, 24, 48], [(6, 6), (12, 12), (24, 22)]],
            [13, 4, [1, 3, 6, 12, 24], [(13, 2), (15, 2)]],
            [8, 4, [1, 3, 6, 12], [(8, 1), (9, 3)]],
            [2, 4, [1, 3, 6], [(2, 1), (3, 3)]],
            [2, 1, [1, 3], [(2, 1)]],

            [20, 9, [1, 2, 4, 12, 36], [(20, 4), (24, 5)]],
            [16, 7, [1, 2, 6, 12, 36], [(16, 2), (18, 5)]],
            [16, 7, [1, 3, 6, 12, 36], [(16, 2), (18, 5)]],

            [4, 12, [1, 2, 6, 18, 36], [(4, 2), (6, 10)]],
            [13, 3, [1, 3, 6, 18, 36], [(13, 2), (15, 1)]],

            [4, 12, [1, 3, 9, 18, 36], [(4, 2), (6, 3), (9, 7)]],

            [14, 25, [1, 2, 6, 18, 54], [(14, 4), (18, 21)]],
            [8, 16, [1, 3, 6, 18, 54], [(8, 1), (9, 3), (12, 6), (18, 6)]],
            [8, 15, [1, 3, 9, 18, 54], [(8, 1), (9, 9), (18, 5)]],
            [12, 30, [1, 3, 9, 27, 54], [(12, 6), (18, 9), (27, 15)]],

            [4, 9, [1, 3, 9, 27], [(4, 2), (6, 3), (9, 4)]],

        ]

        for entry in testCasesForAllPlausibleSimpleMeters:
            testCase = ReGrouper(entry[0], entry[1], pulseLengths=entry[2])
            self.assertEqual(testCase.offsetDurationPairs, entry[3])

    def testSplitSameLevel(self):
        """
        Tests the splitSameLevel parameter with a cases in 6/8.
        """
        testCase1 = ReGrouper(0.5, 1, timeSignature='6/8', splitSameLevel=False)
        self.assertEqual(testCase1.offsetDurationPairs, [(0.5, 1)])
        testCase2 = ReGrouper(0.5, 1, timeSignature='6/8', splitSameLevel=True)
        self.assertEqual(testCase2.offsetDurationPairs, [(0.5, 0.5), (1, 0.5)])

        testCase1 = ReGrouper(0.5, 2, timeSignature='6/8', splitSameLevel=False)
        self.assertEqual(testCase1.offsetDurationPairs, [(0.5, 1), (1.5, 1)])
        testCase2 = ReGrouper(0.5, 2, timeSignature='6/8', splitSameLevel=True)
        self.assertEqual(testCase2.offsetDurationPairs, [(0.5, 0.5), (1, 0.5), (1.5, 1)])


# -----------------------------------------------------------------------------

if __name__ == '__main__':
    unittest.main()
