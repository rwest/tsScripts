import os
import logging
import openbabel
from subprocess import Popen

import rmgpy
from rmgpy.molecule import Molecule
from rmgpy.qm.main import QMCalculator
from rmgpy.qm.molecule import Geometry
from rmgpy.qm.reaction import QMReaction

from collections import defaultdict

import rdkit

"""
degeneracy = 2
CC=C[C]=C to C(=C[CH2])C=C
"""
family = 'intra_H_migration'

reactant = """
1  *2 C 0 {2,S} {6,S} {7,S} {8,S}
2  *5 C 0 {1,S} {3,D} {9,S}
3  *4 C 0 {2,D} {5,S} {10,S}
4     C 0 {5,D} {11,S} {12,S}
5  *1 C 1 {3,S} {4,D}
6  *3 H 0 {1,S}
7     H 0 {1,S}
8     H 0 {1,S}
9     H 0 {2,S}
10    H 0 {3,S}
11    H 0 {4,S}
12    H 0 {4,S}
"""

product = """
1  *4 C 0 {2,D} {3,S} {8,S}
2  *5 C 0 {1,D} {4,S} {7,S}
3  *1 C 0 {1,S} {5,D} {6,S}
4  *2 C 1 {2,S} {9,S} {10,S}
5     C 0 {3,D} {11,S} {12,S}
6  *3 H 0 {3,S}
7     H 0 {2,S}
8     H 0 {1,S}
9     H 0 {4,S}
10    H 0 {4,S}
11    H 0 {5,S}
12    H 0 {5,S}
"""

actions = [
            ['BREAK_BOND', '*2', 'S', '*3'],
            ['FORM_BOND', '*1', 'S', '*3'],
            ['GAIN_RADICAL', '*2', '1'],
            ['LOSE_RADICAL', '*1', '1']
            ]
#########################################################################

inputFileExtension = '.gjf'
outputFileExtension = '.out'
executablePath = os.path.join(os.getenv('GAUSS_EXEDIR') , 'g09')
attempt = 1

usePolar = False

keywords = [
            "# pm3 opt=(verytight,gdiis) freq IOP(2/16=3)",
            "# pm3 opt=(verytight,gdiis) freq IOP(2/16=3) IOP(4/21=2)",
            "# pm3 opt=(verytight,calcfc,maxcyc=200) freq IOP(2/16=3) nosymm" ,
            "# pm3 opt=(verytight,calcfc,maxcyc=200) freq=numerical IOP(2/16=3) nosymm",
            "# pm3 opt=(verytight,gdiis,small) freq IOP(2/16=3)",
            "# pm3 opt=(verytight,nolinear,calcfc,small) freq IOP(2/16=3)",
            "# pm3 opt=(verytight,gdiis,maxcyc=200) freq=numerical IOP(2/16=3)",
            "# pm3 opt=tight freq IOP(2/16=3)",
            "# pm3 opt=tight freq=numerical IOP(2/16=3)",
            "# pm3 opt=(tight,nolinear,calcfc,small,maxcyc=200) freq IOP(2/16=3)",
            "# pm3 opt freq IOP(2/16=3)",
            "# pm3 opt=(verytight,gdiis) freq=numerical IOP(2/16=3) IOP(4/21=200)",
            "# pm3 opt=(calcfc,verytight,newton,notrustupdate,small,maxcyc=100,maxstep=100) freq=(numerical,step=10) IOP(2/16=3) nosymm",
            "# pm3 opt=(tight,gdiis,small,maxcyc=200,maxstep=100) freq=numerical IOP(2/16=3) nosymm",
            "# pm3 opt=(tight,gdiis,small,maxcyc=200,maxstep=100) freq=numerical IOP(2/16=3) nosymm",
            "# pm3 opt=(verytight,gdiis,calcall,small,maxcyc=200) IOP(2/16=3) IOP(4/21=2) nosymm",
            "# pm3 opt=(verytight,gdiis,calcall,small) IOP(2/16=3) nosymm",
            "# pm3 opt=(calcall,small,maxcyc=100) IOP(2/16=3)",
            ]

@property
def scriptAttempts():
    "The number of attempts with different script keywords"
    return len(keywords)

@property
def maxAttempts():
    "The total number of attempts to try"
    return 2 * len(keywords)

def inputFileKeywords(attempt):
    """
    Return the top keywords for attempt number `attempt`.

    NB. `attempt`s begin at 1, not 0.
    """
    assert attempt <= maxAttempts
    if attempt > scriptAttempts:
        attempt -= scriptAttempts
    return keywords[attempt-1]

def run():
    # submits the input file to Gaussian
    process = Popen([executablePath, inputFilePath, outputFilePath])
    process.communicate()# necessary to wait for executable termination!

def atoms(mol):
    atoms = {}
    for atom in mol:
        args = atom.split()
        index = int(args.pop(0))
        if '*' in args[0]:
            label = args.pop(0)
        else:
            label = '  '
        type = args.pop(0)
        rad = args.pop(0)
        bonds = {}
        while args:
            bond = args.pop(0)[1:-1].split(',')
            bonds[int(bond[0])] = bond[1]
        atoms[index] = {'label': label, 'type': type,
                        'rad': rad, 'bonds': bonds}
    return atoms

def adjlist(atoms):
    str = ''
    for key in atoms:
        atom = atoms[key]
        str += '\n{0:<{1}}{2}'.format(key,
                                      len('{0}'.format(max(atoms.keys()))) + 1,
                                      atom['label'])
        str += ' {0} {1}'.format(atom['type'], atom['rad'])
        for key0 in sorted(atom['bonds'].keys()):
            str += ' {' + '{0},{1}'.format(key0, atom['bonds'][key0]) + '}'
    return str.strip() + '\n'

def bondForm(fullString, otherIdx, bond):
    fullString = fullString + ' {' + str(otherIdx) + ',' + bond + '}'
    
    return fullString
    
def bondBreak(fullString, otherIdx):
    splits = fullString.split('{')
    i = 0
    for lineSplit in splits:
        if lineSplit.split(',')[0] == str(otherIdx):
            splits.pop(i)
        i += 1
    fullString = splits[0]
    for k in range(1, len(splits)):
        fullString = fullString + '{' + splits[k]
    return fullString

def radChange(fullString, action, decrease = False):
    
    radChg = fullString[8]
    if decrease:
        radNum = int(radChg) - int(action)
    else:
        radNum = int(radChg) + int(action)
    radNum = str(radNum)
    fullString = fullString.replace(' ' + radChg + ' ', ' ' + radNum + ' ')
    
    return fullString

def matchAtoms(reactant):
    newadjlist = reactant.toAdjacencyList().strip().splitlines()
    radjlist = reactant.toAdjacencyList().strip().splitlines()
    rdict = {}
    for line in radjlist:
        if line.find('*') > -1:
            rdict[line.split()[1]] = int(line.split()[0])
    
    for action in actions:
        if action[0].lower() == 'break_bond':
            idx1 = rdict[action[1]]
            idx2 = rdict[action[3]]
            
            edit1 = newadjlist.pop(idx1 - 1)
            edit1 = bondBreak(edit1, idx2)
            newadjlist.insert(idx1 - 1, edit1)
            
            edit2 = newadjlist.pop(idx2 - 1)
            edit2 = bondBreak(edit2, idx1)
            newadjlist.insert(idx2 - 1, edit2)
        elif action[0].lower() == 'form_bond':
            idx1 = rdict[action[1]]
            idx2 = rdict[action[3]]
            
            edit1 = newadjlist.pop(idx1 - 1)
            edit1 = bondForm(edit1, idx2, action[2])
            newadjlist.insert(idx1 - 1, edit1)
            
            edit2 = newadjlist.pop(idx2 - 1)
            edit2 = bondForm(edit2, idx1, action[2])
            newadjlist.insert(idx2 - 1, edit2)
        elif action[0].lower() == 'gain_radical':
            idx = rdict[action[1]]
            
            edit = newadjlist.pop(idx - 1)
            edit = radChange(edit, action[2])
            newadjlist.insert(idx - 1, edit)
        elif action[0].lower() == 'lose_radical':
            idx = rdict[action[1]]
            
            edit = newadjlist.pop(idx - 1)
            edit = radChange(edit, action[2], decrease = True)
            newadjlist.insert(idx - 1, edit)
    return newadjlist
        
def writeInputFile():
    """
    Using the :class:`Geometry` object, write the input file
    for the `attmept`th attempt.
    """

    obConversion = openbabel.OBConversion()
    obConversion.SetInAndOutFormats("mol", "gjf")
    mol = openbabel.OBMol()

    obConversion.ReadFile(mol, molFilePathForCalc )

    mol.SetTitle(geometry.uniqueIDlong)
    obConversion.SetOptions('k', openbabel.OBConversion.OUTOPTIONS)
    input_string = obConversion.WriteString(mol)
    chk_file = '%chk=' + chkFilePath
    top_keys = inputFileKeywords(attempt)
    with open(inputFilePath, 'w') as gaussianFile:
        gaussianFile.write(chk_file)
        gaussianFile.write('\n')
        gaussianFile.write(top_keys)
        gaussianFile.write(input_string)
        gaussianFile.write('\n')

def writeQST2InputFile():
    obrConversion = openbabel.OBConversion()
    obrConversion.SetInAndOutFormats("mol", "gjf")
    molR = openbabel.OBMol()
    obrConversion.ReadFile(molR, rmolFilePathForCalc )
    molR.SetTitle(geometryR.uniqueIDlong)
    obrConversion.SetOptions('k', openbabel.OBConversion.OUTOPTIONS)
    
    obpConversion = openbabel.OBConversion()
    obpConversion.SetInAndOutFormats("mol", "gjf")
    molP = openbabel.OBMol()
    obpConversion.ReadFile(molP, pmolFilePathForCalc )
    molP.SetTitle(geometryP.uniqueIDlong)
    obpConversion.SetOptions('k', openbabel.OBConversion.OUTOPTIONS)
    
    # all of the first molecule, and remove the first 2 lines (the '\n') from the second
    input_string = obrConversion.WriteString(molR) + obpConversion.WriteString(molP)[2:]
    top_keys = "# pm3 opt=(qst2) nosymm"
    with open(inputFilePath, 'w') as gaussianFile:
        gaussianFile.write(top_keys)
        gaussianFile.write(input_string)
        gaussianFile.write('\n')

def writeModRedundantFile():
    chk_file = '%chk=' + chkFilePath
    top_keys = "# pm3 opt=(modredundant) geom=(allcheck) guess=check nosymm"
    bottom_keys = 'B 1 2 += 0.1 F'
    with open(inputFilePath, 'w') as gaussianFile:
        gaussianFile.write(chk_file)
        gaussianFile.write('\n')
        gaussianFile.write(top_keys)
        gaussianFile.write('\n\n')
        gaussianFile.write(bottom_keys)
        gaussianFile.write('\n')
        
def writeModRedundantFile1():
    obConversion = openbabel.OBConversion()
    obConversion.SetInAndOutFormats("mol", "gjf")
    mol = openbabel.OBMol()
    
    obConversion.ReadFile(mol, molFilePathForCalc )
    
    mol.SetTitle(geometry.uniqueIDlong)
    obConversion.SetOptions('k', openbabel.OBConversion.OUTOPTIONS)
    input_string = obConversion.WriteString(mol)
    chk_file = '%chk=' + chkFilePath
    top_keys = "# pm3 opt=(modredundant) nosymm"
    bottom_keys1 = 'B 4 9 += 0.1 F'
    bottom_keys2 = 'B 5 9 += -0.1 F'
    with open(inputFilePath, 'w') as gaussianFile:
        gaussianFile.write(chk_file)
        gaussianFile.write('\n')
        gaussianFile.write(top_keys)
        gaussianFile.write(input_string)
        gaussianFile.write(bottom_keys1)
        gaussianFile.write('\n')
        gaussianFile.write(bottom_keys2)
        gaussianFile.write('\n')
        
def writeModRedundantFile2():
    chk_file = '%chk=' + chkFilePath
    top_keys = "# pm3 opt=(modredundant) geom=(allcheck) guess=check nosymm"
    bottom_keys1 = 'B 4 9 += 0.1 F'
    bottom_keys2 = 'B 5 9 += -0.1 F'
    with open(inputFilePath, 'w') as gaussianFile:
        gaussianFile.write(chk_file)
        gaussianFile.write('\n')
        gaussianFile.write(top_keys)
        gaussianFile.write('\n\n')
        gaussianFile.write(bottom_keys1)
        gaussianFile.write('\n')
        gaussianFile.write(bottom_keys2)
        gaussianFile.write('\n')
            
def convertOutputToInput():
    obConversion = openbabel.OBConversion()
    obConversion.SetInAndOutFormats("g09", "gjf")
    mol = openbabel.OBMol()
    
    obConversion.ReadFile(mol, outputFilePath)
    
    mol.SetTitle(geometry.uniqueIDlong)
    obConversion.SetOptions('k', openbabel.OBConversion.OUTOPTIONS)
    input_string = obConversion.WriteString(mol)
    chk_file = '%chk=' + chkFilePath
    top_keys = "# pm3 opt=(modredundant)"
    bottom_keys = '1 2 F'
    with open(inputFilePath, 'w') as gaussianFile:
        gaussianFile.write(chk_file)
        gaussianFile.write('\n')
        gaussianFile.write(top_keys)
        gaussianFile.write(input_string)
        gaussianFile.write('\n')
        gaussianFile.write(bottom_keys)
        gaussianFile.write('\n')

def generateKineticData():
    pass
    
#########################################################################

reactant = Molecule().fromAdjacencyList(reactant)
newadjlist = matchAtoms(reactant)
padjlist = adjlist(atoms(newadjlist))
product = Molecule().fromAdjacencyList(padjlist)

quantumMechanics = QMCalculator()
quantumMechanics.settings.software = 'gaussian'
quantumMechanics.settings.fileStore = 'QMfiles'
quantumMechanics.settings.scratchDirectory = None
quantumMechanics.settings.onlyCyclics = True
quantumMechanics.settings.maxRadicalNumber = 0

qmcalcR = rmgpy.qm.gaussian.GaussianMolPM3(reactant, quantumMechanics.settings)
sorted_atom_list = product.vertices[:]
qmcalcP = rmgpy.qm.gaussian.GaussianMolPM3(product, quantumMechanics.settings)
product.vertices = sorted_atom_list

qmcalcR.createGeometry()
qmcalcP.createGeometry()

geometryR = qmcalcR.geometry
geometryP = qmcalcP.geometry

rinputFilePath = qmcalcR.inputFilePath
rmolFilePathForCalc = qmcalcR.getMolFilePathForCalculation(attempt)

pinputFilePath = qmcalcP.inputFilePath
pmolFilePathForCalc = qmcalcP.getMolFilePathForCalculation(attempt)

inputFilePath = rinputFilePath

writeQST2InputFile()
# writeInputFile()
# run()
# # i = 1
# qmreact = QMReaction()
# rdMol, tsBM, mult = qmreact.generateBoundsMatrix(tsBase, quantumMechanics.settings)
# for action in actions:
#     if action[0].lower() == 'break_bond':
#         mk1 = action[1]
#         mk2 = action[3]
#     elif action[0].lower() == 'form_bond':
#         mk3 = action[1]
#         mk4 = action[3]
# 
# if mk1 == mk3:
#     lbl1 = mk1
#     lbl2 = mk2
#     lbl3 = mk4
# elif mk1 == mk4:
#     lbl1 = mk1
#     lbl2 = mk2
#     lbl3 = mk3
# elif mk2 == mk3:
#     lbl1 = mk2
#     lbl2 = mk1
#     lbl3 = mk4
# elif mk2 == mk4:
#     lbl1 = mk2
#     lbl2 = mk1
#     lbl3 = mk3
# 
# lbl1 = tsBase.getLabeledAtom(lbl1).sortingLabel
# lbl2 = tsBase.getLabeledAtom(lbl2).sortingLabel
# lbl3 = tsBase.getLabeledAtom(lbl3).sortingLabel
# 
# if tsBM[lbl1][lbl2] > tsBM[lbl2][lbl1]:
#     testDist = 3 * tsBM[lbl1][lbl2]
# else:
#     testDist = 3 * tsBM[lbl2][lbl1]
# 
# if tsBM[lbl1][lbl3] > tsBM[lbl3][lbl1]:
#     if tsBM[lbl1][lbl3] > testDist:
#         tsBM[lbl1][lbl3] = testDist
# else:
#     if tsBM[lbl3][lbl1] > testDist:
#         tsBM[lbl3][lbl1] = testDist
# 
# rdkit.DistanceGeometry.DoTriangleSmoothing(tsBM)
# 
# tsGeom = Geometry(quantumMechanics.settings, 'transitionState', tsBase, mult)
# tsGeom.generateRDKitGeometries(tsBM)
# 
# molFilePathForCalc = tsGeom.getRefinedMolFilePath()
# inputFilePath = 'QMfiles/transitionState.gjf'
# outputFilePath = 'QMfiles/transitionState.log'
# chkFilePath = 'QMfiles/transitionState'
# 
# import ipdb; ipdb.set_trace()
# writeModRedundantFile2()
# while i in range(1, 11):
#     
#     convertOutputToInput()
#     run()
#     i += 1