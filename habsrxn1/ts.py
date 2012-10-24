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
CC.[CH3] to [CH2]C.C
"""
family = 'H_Abstraction'

reactant = """
1     C 0 {2,D} {6,S} {7,S}
2     C 0 {1,D} {3,S} {4,S}
3  *1 C 0 {2,S} {5,S} {8,S} {9,S}
4     C 0 {2,S} {10,S} {11,S} {12,S}
5  *2 H 0 {3,S}
6     H 0 {1,S}
7     H 0 {1,S}
8     H 0 {3,S}
9     H 0 {3,S}
10    H 0 {4,S}
11    H 0 {4,S}
12    H 0 {4,S}
13 *3 C 1 {14,S} {18,S} {19,S}
14    C 0 {13,S} {15,S} {17,S} {20,S}
15    C 0 {14,S} {16,S} {21,S} {22,S}
16    O 0 {15,S} {23,S}
17    C 0 {14,S} {24,S} {25,S} {26,S}
18    H 0 {13,S}
19    H 0 {13,S}
20    H 0 {14,S}
21    H 0 {15,S}
22    H 0 {15,S}
23    H 0 {16,S}
24    H 0 {17,S}
25    H 0 {17,S}
26    H 0 {17,S}
"""

product = """
1     C 0 {2,D} {6,S} {7,S}
2     C 0 {1,D} {3,S} {4,S}
3  *1 C 1 {2,S} {8,S} {9,S}
4     C 0 {2,S} {10,S} {11,S} {12,S}
5  *2 H 0 {13,S}
6     H 0 {1,S}
7     H 0 {1,S}
8     H 0 {3,S}
9     H 0 {3,S}
10    H 0 {4,S}
11    H 0 {4,S}
12    H 0 {4,S}
13 *3 C 0 {5,S} {14,S} {18,S} {19,S}
14    C 0 {13,S} {15,S} {17,S} {20,S}
15    C 0 {14,S} {16,S} {21,S} {22,S}
16    O 0 {15,S} {23,S}
17    C 0 {14,S} {24,S} {25,S} {26,S}
18    H 0 {13,S}
19    H 0 {13,S}
20    H 0 {14,S}
21    H 0 {15,S}
22    H 0 {15,S}
23    H 0 {16,S}
24    H 0 {17,S}
25    H 0 {17,S}
26    H 0 {17,S}
"""

actions = [
            ['BREAK_BOND', '*1', 'S', '*2'],
            ['FORM_BOND', '*2', 'S', '*3'],
            ['GAIN_RADICAL', '*1', '1'],
            ['LOSE_RADICAL', '*3', '1']
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

def fixSortLabel(molecule):
    """
    This may not be required anymore. Was needed as when molecules were created, the
    rmg sorting labels would be set after where we tried to generate the TS.
    """
    sortLbl = 0
    for vertex in molecule.vertices:
        vertex.sortingLabel = sortLbl
        sortLbl += 1
    return molecule

def getGeometry(molecule, settings):

    multiplicity = sum([i.radicalElectrons for i in molecule.atoms]) + 1
    geom = Geometry(settings, molecule.toAugmentedInChIKey(), molecule, multiplicity)

    return geom, multiplicity

def getRDKitMol(geometry):
    """
    Check there is no RDKit mol file already made. If so, use rdkit to make a rdmol from
    a mol file. If not, make rdmol from geometry.
    """ 
    if not os.path.exists(geometry.getCrudeMolFilePath()):
        geometry.generateRDKitGeometries()
    rdKitMol = rdkit.Chem.MolFromMolFile(geometry.getCrudeMolFilePath(), removeHs=False)      

    return rdKitMol

def generateBoundsMatrix(molecule, settings):
    """
    Uses rdkit to generate the bounds matrix of a rdkit molecule.
    """
    geometry, multiplicity = getGeometry(molecule, settings)
    rdKitMol = getRDKitMol(geometry)
    boundsMatrix = rdkit.Chem.rdDistGeom.GetMoleculeBoundsMatrix(rdKitMol)

    return rdKitMol, boundsMatrix, multiplicity

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
    chk_file = '%chk=' + inputFilePath.split('.')[0]
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
    top_keys = "# pm6 opt=(qst2,nofreeze,calcall,tight,noeigentest) nosymm"
    with open(inputFilePath, 'w') as gaussianFile:
        gaussianFile.write(chk_file)
        gaussianFile.write('\n')
        gaussianFile.write(top_keys)
        gaussianFile.write(input_string)
        gaussianFile.write('\n')

def writeTSInputFile():
    chk_file = '%chk=' + inputFilePath.split('.')[0]
    top_keys = "# pm6 opt=(ts,nofreeze,calcall,tight,noeigentest) geom=allcheck guess=check nosymm"
    title = ' ' + geometryR.uniqueIDlong + ' ' + geometryP.uniqueIDlong
    with open(inputFilePath, 'w') as gaussianFile:
        gaussianFile.write(chk_file)
        gaussianFile.write('\n')
        gaussianFile.write(top_keys)
        gaussianFile.write('\n\n')
        gaussianFile.write(title)
        gaussianFile.write('\n\n')

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

def editMatrix(bm, lbl1, lbl2, num, diff):
    if bm[lbl1][lbl2] > bm[lbl2][lbl1]:
        bm[lbl2][lbl1] = num
        bm[lbl1][lbl2] = bm[lbl2][lbl1] + diff
    else:
        bm[lbl1][lbl2] = num
        bm[lbl2][lbl1] = bm[lbl1][lbl2] + diff
    
    return bm
        
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
quantumMechanics.settings.scratchDirectory = 'scratch'
quantumMechanics.settings.onlyCyclics = False
quantumMechanics.settings.maxRadicalNumber = 0

reactant = fixSortLabel(reactant)
product = fixSortLabel(product)

rRDMol, rBM, rMult = generateBoundsMatrix(reactant, quantumMechanics.settings)
pRDMol, pBM, pMult = generateBoundsMatrix(product, quantumMechanics.settings)

#edit bounds distances to align reacting atoms
if family.lower() == 'h_abstraction':
    lbl1 = reactant.getLabeledAtom('*1').sortingLabel
    lbl2 = reactant.getLabeledAtom('*2').sortingLabel
    lbl3 = reactant.getLabeledAtom('*3').sortingLabel
    
    rBM = editMatrix(rBM, lbl1, lbl3, 2.5, 0.2)
    rBM = editMatrix(rBM, lbl2, lbl3, 2.0, 0.1)
    
    pBM = editMatrix(pBM, lbl1, lbl2, 2.0, 0.1)
    pBM = editMatrix(pBM, lbl1, lbl3, 2.5, 0.2)

for i in range(0, len(rBM)):
        for k in range(0, len(rBM)):
            if rBM[i][k] == 1000.:
                rBM[i][k] = 2 * rBM[k][i]
            if pBM[i][k] == 1000.:
                pBM[i][k] = 2 * pBM[k][i]

rdkit.DistanceGeometry.DoTriangleSmoothing(rBM)
rdkit.DistanceGeometry.DoTriangleSmoothing(pBM)

rsorted_atom_list = reactant.vertices[:]
psorted_atom_list = product.vertices[:]
qmcalcR = rmgpy.qm.gaussian.GaussianMolPM3(reactant, quantumMechanics.settings)
qmcalcP = rmgpy.qm.gaussian.GaussianMolPM3(product, quantumMechanics.settings)
reactant.vertices = rsorted_atom_list
product.vertices = psorted_atom_list

qmcalcR.createGeometry(rBM)
qmcalcP.createGeometry(pBM)

geometryR = qmcalcR.geometry
geometryP = qmcalcR.geometry

rinputFilePath = qmcalcR.inputFilePath
routputFilePath = qmcalcR.outputFilePath
rmolFilePathForCalc = qmcalcR.getMolFilePathForCalculation(attempt)

pinputFilePath = qmcalcP.inputFilePath
poutputFilePath = qmcalcR.outputFilePath
pmolFilePathForCalc = qmcalcP.getMolFilePathForCalculation(attempt)

inputFilePath = rinputFilePath
outputFilePath = poutputFilePath
import ipdb; ipdb.set_trace()
writeQST2InputFile()
run()
writeTSInputFile()
#import ipdb; ipdb.set_trace()
run()
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