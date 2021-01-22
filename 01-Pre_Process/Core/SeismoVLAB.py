#!/usr/bin/python3
# -*- coding: Utf-8 -*-

import os
import sys
import math
import copy
import numpy as np
from Method.Attach import *
from Method.Remove import *
from Method.Display import *
from Method.Builder import *
from Method.Compute import *
from Parser.Formats import *
from Core.Outputs import *
from Core.Utilities import *
from Core.Numberer import *
from Core.Partition import *
from Core.PlaneWave import *
from Core.Definitions import *

def createFolders():
    """
    This function creates all required folders, these are:
       'Partition' : Strores the domain decomposition and SVL Run-Analysis files
       'Paraview'  : Stores the ParaView VTK animation files for a given load combination
       'Solution'  : Stores the recorded responses for a given load combination
    @visit  https://github.com/SeismoVLAB/SVL\n
    @author Danilo S. Kusanovic 2020

    Returns
    -------
    None
    """
    #Creates the Partition/Paraview/Results folders
    for folder in ['Partition','Paraview','Solution']:
        dirName  = Options['path'] + '/' + folder
        if not os.path.exists(dirName):
            os.mkdir(dirName)

    #Creates the Load combination folders used in Results/Paraview 
    for cTag in Entities['Combinations']:
        for folder in ['Solution','Paraview']:
            dirName  = Options['path'] + '/' + folder + '/' + Entities['Combinations'][cTag]['attributes']['folder']
            if not os.path.exists(dirName):
                os.mkdir(dirName)

def Entities2Processor(matSubdomain, secSubdomain, nodeSubdomain, massSubdomain, conSubdomain, elemSubdomain, k):
    """
    This function creates a dictionary that holds all information required to
    be written in the k-th processor  
    @visit  https://github.com/SeismoVLAB/SVL\n
    @author Danilo S. Kusanovic 2020

    Parameters
    ----------
    matSubdomain  : list
        The material indexes tha belongs to the k-th partition
    secSubdomain  : list
        The section indexes tha belongs to the k-th partition
    nodeSubdomain : list
        The node indexes tha belongs to the k-th partition
    conSubdomain  : list
        The constraint indexes tha belongs to the k-th partition
    elemSubdomain : list
        The material indexes tha belongs to the k-th partition
    loadSubdomain : list
        The load indexes tha belongs to the k-th partition
    k : int
        The processor (partition) number

    Returns
    -------
    ToProcessor : dict
        Contains all Entities (information) that belongs to this process
    """
    #Empty dictionary to be written
    ToProcessor = {
        'Global'      : {}, 
        'Materials'   : {}, 
        'Sections'    : {}, 
        'Nodes'       : {}, 
        'Masses'      : {}, 
        'Supports'    : {}, 
        'Constraints' : {}, 
        'Elements'    : {}, 
        'Dampings'    : {}, 
        'Loads'       : {}, 
        'Combinations': {}, 
        'Recorders'   : {},
        'Simulations' : {}
        }
    
    #Global parameters stored in Entities for simulation
    ToProcessor['Global'] = {'ndim': Options['dimension'], 'ntotal': Options['ntotal'], 'nfree': Options['nfree'], 'mass': Options['massform'].upper()} 

    #Gets the materials for this partition
    for tag in matSubdomain:
        ToProcessor['Materials'][str(tag)] = Entities['Materials'][tag]

    #Gets the sections for this partition
    for tag in secSubdomain:
        ToProcessor['Sections'][str(tag)] = Entities['Sections'][tag]

    #Gets the nodes for this partition
    nTags = sorted(nodeSubdomain)
    for tag in nTags:
        ToProcessor['Nodes'][str(tag)] = Entities['Nodes'][tag]

    #Gets the point masses for this partition
    nTags = sorted(massSubdomain.intersection(nodeSubdomain))
    for tag in nTags:
        ToProcessor['Masses'][str(tag)] = copy.deepcopy(Entities['Masses'][tag])
        massSubdomain.remove(tag)

    #Gets the support motions for this partition
    sTags = set(Entities['Supports'].keys())
    nTags = sorted(sTags.intersection(nodeSubdomain))
    for tag in nTags:
        ToProcessor['Supports'][str(tag)] = Entities['Supports'][tag]

    #Gets the constraints for this partition
    cTags = sorted(conSubdomain, reverse=True)
    for tag in cTags:
        ToProcessor['Constraints'][str(tag)] = Entities['Constraints'][tag]

    #Gets the elements for this partition
    for tag in elemSubdomain:
        ToProcessor['Elements'][str(tag)] = Entities['Elements'][tag]

    #Gets the dampings for this partition
    for dTag in Entities['Dampings']:
        eTag = list(set(elemSubdomain).intersection(Entities['Dampings'][dTag]['attributes']['list']))
        if eTag:
             ToProcessor['Dampings'][str(dTag)] = copy.deepcopy(Entities['Dampings'][dTag])
             ToProcessor['Dampings'][str(dTag)]['attributes']['list'] = eTag

    #Gets the loads for this partition
    loadSubdomain = list()
    for lTag in Entities['Loads']:
        if Entities['Loads'][lTag]['name'] == 'POINTLOAD':
            nTags = sorted(nodeSubdomain.intersection(Entities['Loads'][lTag]['attributes']['list']))
            if nTags:
                loadSubdomain.append(lTag)
                ToProcessor['Loads'][str(lTag)] = copy.deepcopy(Entities['Loads'][lTag])
                ToProcessor['Loads'][str(lTag)]['attributes']['list'] = nTags
                Entities['Loads'][lTag]['attributes']['list'] = list(set(Entities['Loads'][lTag]['attributes']['list']).difference(nTags))
        elif Entities['Loads'][lTag]['name'] == 'ELEMENTLOAD':
            eTags = sorted(list(set(elemSubdomain).intersection(Entities['Loads'][lTag]['attributes']['list'])))
            if eTags:
                ToProcessor['Loads'][str(lTag)] = copy.deepcopy(Entities['Loads'][lTag])
                ToProcessor['Loads'][str(lTag)]['attributes']['list'] = eTags
                loadSubdomain.append(lTag)
        elif Entities['Loads'][lTag]['name'] == 'SUPPORTMOTION':
            nTags = sorted(nodeSubdomain.intersection(Entities['Loads'][lTag]['attributes']['list']))
            if nTags:
                ToProcessor['Loads'][str(lTag)] = copy.deepcopy(Entities['Loads'][lTag])
                ToProcessor['Loads'][str(lTag)]['attributes']['list'] = nTags
                loadSubdomain.append(lTag)

    #Gets the load combinations for this partition
    for cTag in Entities['Combinations']:
        name = Entities['Combinations'][cTag]['name']

        lTag = list(set(Entities['Combinations'][cTag]['attributes']['load']).intersection(loadSubdomain))
        if lTag:
            load    = Entities['Combinations'][cTag]['attributes']['load']
            factors = Entities['Combinations'][cTag]['attributes']['factor']
            folder  = Entities['Combinations'][cTag]['attributes']['folder']
            attributes = {'folder': folder, 'load': [], 'factor': []}
            for j in loadSubdomain:
                for i in range(len(load)):
                    if load[i] == j:
                        attributes['load'].append(load[i])
                        attributes['factor'].append(factors[i])
        else:
             attributes = {}
        ToProcessor['Combinations'][str(cTag)] = {'name': name, 'attributes': attributes}

    #Gets the recorders for this partition
    for rTag in Entities['Recorders']:
        #Modifies the Output File to be consistent with Partition
        OUTFILE = Entities['Recorders'][rTag]['file']
        OUTFILE = OUTFILE.replace(".", '.' + str(k) + '.')
        
        if Entities['Recorders'][rTag]['name'] == 'NODE':
            nTags = sorted(nodeSubdomain.intersection(Entities['Recorders'][rTag]['list']))
            if nTags:
                ToProcessor['Recorders'][str(rTag)] = copy.deepcopy(Entities['Recorders'][rTag])
                ToProcessor['Recorders'][str(rTag)]['file'] = OUTFILE
                ToProcessor['Recorders'][str(rTag)]['list'] = nTags.copy()
        elif Entities['Recorders'][rTag]['name'] == 'ELEMENT':
            eTags = sorted(list(set(elemSubdomain).intersection(Entities['Recorders'][rTag]['list'])))
            if eTags:
                ToProcessor['Recorders'][str(rTag)] = copy.deepcopy(Entities['Recorders'][rTag])
                ToProcessor['Recorders'][str(rTag)]['file'] = OUTFILE
                ToProcessor['Recorders'][str(rTag)]['list'] = eTags.copy()
        elif Entities['Recorders'][rTag]['name'] == 'PARAVIEW':
            OUTFILE = Entities['Recorders'][rTag]['file']
            OUTFILE = OUTFILE.split('.')
            OUTFILE = OUTFILE[0] + '_PART' + str(k)
            ToProcessor['Recorders'][str(rTag)] = copy.deepcopy(Entities['Recorders'][rTag])
            ToProcessor['Recorders'][str(rTag)]['file'] = OUTFILE

    #Gets the simulation for this partition
    for sTag in Entities['Simulations']:
        ctag = Entities['Simulations'][sTag]['combo']

        tag = Entities['Simulations'][sTag]['attributes']['analysis']
        analysis = Entities['Analyses'][tag]

        tag = Entities['Simulations'][sTag]['attributes']['algorithm']
        algorithm = Entities['Algorithms'][tag]

        tag = Entities['Simulations'][sTag]['attributes']['integrator']
        integrator = Entities['Integrators'][tag]

        tag = Entities['Simulations'][sTag]['attributes']['solver']
        solver = Entities['Solvers'][tag]

        attributes = {'analysis': analysis, 'algorithm': algorithm, 'integrator': integrator, 'solver': solver}
        ToProcessor['Simulations'][sTag] = {'combo': ctag, 'attributes': attributes} 

    #Removes the empty fields
    if Options['format'].upper() == 'JSON':
        keys = list(ToProcessor.keys())
        for key in keys:
            if not ToProcessor[key]:
                del ToProcessor[key]
    return ToProcessor

def createPartitions():
    """
    This function creates the partitions according with the pattern generated
    during the domain decomposition. Basically, goes over the Entities and 
    extract the information\n
    @visit  https://github.com/SeismoVLAB/SVL\n
    @author Danilo S. Kusanovic 2020

    Returns
    -------
    None
    """
    #Creates the required folder
    createFolders()

    #Creates the domain decomposition input files
    SetMetisInputFile()

    #Reads the generated domain decomposition results
    GetMetisOutputFile()

    eTags = np.zeros(len(Entities['Elements']), dtype=np.uint32)
    for k, tag in enumerate(Entities['Elements']):
        eTags[k] = tag

    massSubdomain = set(Entities['Masses'].keys())

    #Writes the mesh file 
    for k in range(Options['nparts']):
        #Element that belong to this partition
        elemSubdomain = eTags[Options['partition'] == k]

        #Check if the partition has Element
        if len(elemSubdomain) == 0:
            print('\x1B[31m ERROR \x1B[0m: The partition for processor [%s] does not have Element' % k)
            print("\x1B[31m **************** THE PROCESS WILL BE ABORTED ****************\x1B[0m\n")
            sys.exit(-1)

        #Nodes that belong to this partition
        nodeSubdomain = set() 
        for eTag in elemSubdomain:
            connection = Entities['Elements'][eTag]['conn']
            for nTag in connection:
                nodeSubdomain.add(nTag)

        #Materials that belong to this partition
        matSubdomain = set()
        for eTag in elemSubdomain:
            if 'material' in Entities['Elements'][eTag]['attributes']:
                matSubdomain.add(Entities['Elements'][eTag]['attributes']['material']) 

        #Sections that belong to this partition
        secSubdomain = set() 
        for eTag in elemSubdomain:
            if 'section' in Entities['Elements'][eTag]['attributes']:
                sTag = Entities['Elements'][eTag]['attributes']['section']
                mTag = Entities['Sections'][sTag]['attributes']['material']
                if Entities['Sections'][sTag]['model'] == 'PLAIN':
                    matSubdomain.add(mTag)
                elif  Entities['Sections'][mTag]['model'] == 'FIBER':
                    matSubdomain.update(mTag)
                secSubdomain.add(sTag)

        #Constraints (Equal, General, Diaphragm) that belong to this partition
        conSubdomain = set() 
        for nTag in nodeSubdomain:
            FreeDofs = Entities['Nodes'][nTag]['freedof']
            for dof in FreeDofs:
                if dof < -1:
                    conSubdomain.add(dof)

        #Constraints information must be contained in this partition
        for cTag in conSubdomain:
            Master = Entities['Constraints'][cTag]['mtag']
            for mNode in Master:
                nodeSubdomain.add(mNode)

        #Sets the Entities that belong to this partition
        ToProcessor = Entities2Processor(matSubdomain,secSubdomain,nodeSubdomain,massSubdomain,conSubdomain,elemSubdomain,k)

        #Writes the partition in separated files
        if Options['format'].upper() == 'SVL':
            dict2svl(ToProcessor, k)
        elif Options['format'].upper() == 'JSON':
            dict2json(ToProcessor, k)
    
    #The generated partition file name (generic) path
    Options['execfile'] = Options['file'] + '.$.svl'
    Options['execpath'] = Options['path'] + '/' + 'Partition'

    #SeismoVLAB execution command line
    nparts = Options['nparts']
    if nparts == 1:
        Options['run'] = ' ./SeismoVLAB.exe -dir ' + Options['execpath'] + ' -file ' + Options['execfile'] + '\n'
    elif nparts > 1:
        Options['run'] = ' mpirun -np ' + str(nparts) + ' ./SeismoVLAB.exe -dir ' + Options['execpath'] + ' -file ' + Options['execfile'] + '\n'

    #Cleans generated auxiliar files
    os.remove(Options['execpath'] + '/Graph.out')
    os.remove(Options['execpath'] + '/Graph.out.epart.' + str(nparts))
    os.remove(Options['execpath'] + '/Graph.out.npart.' + str(nparts)) 

def checkWarnings():
    """
    This function checks consistency between the parameters specified by the
    user and the parameters employed in SeismoVLAB. A small report is printed
    showing all possible warnings encounter during the process. If they are 
    found, they are reported as an ALERT to be fixed.\n
    @visit  https://github.com/SeismoVLAB/SVL\n
    @author Danilo S. Kusanovic 2020

    Returns
    -------
    None
    """
    nTags = list(Entities['Nodes'].keys())
    sTags = list(Entities['Sections'].keys())
    mTags = list(Entities['Materials'].keys())
    eTags = list(Entities['Elements'].keys())

    print('\n Checking for warnings:')

    #[1] Check all attributes in NODES are defined in ENTITIES
    if not Entities['Nodes']:
        print("   *** There is no definition of Nodes. ***")
        print("\x1B[31m   *************** THE PROCESS WILL BE ABORTED ***************\x1B[0m\n")
        sys.exit(-1)

    nrestrain = 0
    for nTag in Entities['Nodes']:
        if math.isnan(nTag):
            print("   *** Node[%s] is invalid and should be removed ***" % nTag) 
        if Entities['Nodes'][nTag]['ndof'] == 0:
            print("   *** Node[%s] has ndof=0, fix this or delete it ***" % nTag) 
        ndim = len(Entities['Nodes'][nTag]['coords'])
        if Options['dimension'] != ndim:
            print("   *** Node[%s] coordinate's dimension (=%d) disagrees with Options[\'dimension\'] (=%d) ***" % (nTag,ndim,Options['dimension']))
        for free in Entities['Nodes'][nTag]['freedof']:
            if free == -1:
                nrestrain += 1

    if nrestrain == 0:
        print("   *** There is no restrains applied to Nodes ***")
        print("\x1B[31m   *************** THE PROCESS WILL BE ABORTED ***************\x1B[0m\n")
        sys.exit(-1)

    #[2] Check all attributes in MATERIALS are defined in ENTITIES
    for mTag in Entities['Materials']:
        if math.isnan(mTag):
            print("   *** Material[%s] is invalid and should be removed" % mTag) 
        if Entities['Materials'][mTag]['name'] not in SVLclasses['Materials']:
            print("   *** Material[%s] does not have an appropriate class name (%s) ***" % (mTag,Entities['Materials'][mTag]['name']))

    #[3] Check all attributes in SECTIONS are defined in ENTITIES
    for sTag in Entities['Sections']:
        if math.isnan(sTag):
            print("   *** Section[%s] is invalid and should be removed" % sTag) 
        if Entities['Sections'][sTag]['name'] not in SVLclasses['Sections']:
            print("   *** Section[%s] does not have an appropriate class name (%s) ***" % (sTag,Entities['Sections'][sTag]['name']))

    #[4] Check all attributes in ELEMENTS are defined in ENTITIES
    if not Entities['Elements']:
        print("   *** There is no definition of Elements. ***")
        print("\x1B[31m   *************** THE PROCESS WILL BE ABORTED ***************\x1B[0m\n")
        sys.exit(-1)

    naux = set(nTags)
    for eTag in Entities['Elements']:
        if math.isnan(eTag):
            print("   *** Element[%s] is invalid and should be removed" % nTag) 
        if Entities['Elements'][eTag]['name'] not in SVLclasses['Elements']:
            print("   *** Elements[%s] does not have an appropriate class name (%s) ***" % (nTag,Entities['Elements'][eTag]['name'])) 
        if 'material' in Entities['Elements'][eTag]['attributes']:
            mtag = Entities['Elements'][eTag]['attributes']['material']
            if mtag not in mTags:
                print("   *** Material[%s] has not been defined in Elements[%s] (%s) ***" % (mtag, eTag,Entities['Elements'][eTag]['name'])) 
        if 'section' in Entities['Elements'][eTag]['attributes']:
            stag = Entities['Elements'][eTag]['attributes']['section']
            if stag not in sTags:
                print("   *** Section[%s] has not been defined in Elements[%s] (%s) ***" % (stag, eTag,Entities['Elements'][eTag]['name']))
        defective = set(Entities['Elements'][eTag]['conn']).difference(naux)
        if defective:
            print('   *** Node[%s] have not been defined in Element[%s]' % (', '.join(str(s) for s in defective), eTag))

    #[5] Check all attributes in SURFACES are defined in ENTITIES
    for sTag in Entities['Surfaces']:
        eTag = Entities['Surfaces'][sTag]['etag']
        if eTag in Entities['Elements']:
            name = Entities['Elements'][sTag]['name']
            surf = Entities['Surfaces'][sTag]['conn']
            conn = np.array(Entities['Elements'][sTag]['conn'])
            Entities['Surfaces'][sTag]['face'] = SurfaceFace(VTKelems['VTKsvl'][name], surf, conn)
        else:
            print('   *** Surface[%s] does not belong to Element[%s] ***' % (sTag, eTag))

    #[6] Checks consistency between POINTLOAD/ELEMENTLOAD and other ENTITIES
    for lTag in Entities['Loads']:
        Name = Entities['Loads'][lTag]['name']
        if Name == 'POINTLOAD':
            #Prepare Node indeces for 'ALL' case in list
            if isinstance(Entities['Loads'][lTag]['attributes']['list'], str):
                Entities['Loads'][lTag]['attributes']['list'] = list(Entities['Nodes'].keys())

            #Checks consistency between POINTLOAD and degree-of-freedom in Node
            nTag = Entities['Loads'][lTag]['attributes']['list']
            fTag = Entities['Loads'][lTag]['attributes']['fun']
            nDIR = len(Entities['Functions'][fTag]['attributes']['dir'])
            for n in nTag:
                nDOF = Entities['Nodes'][n]['ndof']
                if nDOF != nDIR:
                    print('   *** Load[%s] (POINTLOAD) with Function[%s] (\'dir\') does not match Node[%s] (\'ndof\') ***' % (lTag,fTag,n))
            
            #Check if TimeSerie file can be opened (local and then global address)
            if 'file' in Entities['Functions'][fTag]['attributes']:
                #Tries the path given by user
                filename = Entities['Functions'][fTag]['attributes']['file']
                if tryOpenfile(filename):
                    #Tries a global path with respect to the main file
                    filepath = Options['path'] + '/' + Entities['Functions'][fTag]['attributes']['file']
                    if tryOpenfile(filepath):
                        lType = Entities['Loads'][lTag]['attributes']['type']
                        print('   *** POINTLOAD (%s) file=\'%s\' in Function[%s] could not be opened ***' % (lType,filename,fTag))
                    else:
                        Entities['Functions'][fTag]['attributes']['file'] = filepath
        elif Name == 'ELEMENTLOAD':
            #Prepare Node indeces for 'ALL' case in list
            if isinstance(Entities['Loads'][lTag]['attributes']['list'], str):
                Entities['Loads'][lTag]['attributes']['list'] = list(Entities['Elements'].keys())

            #Checks consistency between ELEMENTLOAD and model dimension in Options
            fTag = Entities['Loads'][lTag]['attributes']['fun']
            if 'dir' in Entities['Functions'][fTag]['attributes']:
                nDIR = len(Entities['Functions'][fTag]['attributes']['dir'])
                if nDIR != Options['dimension']:
                    print('   *** Load[%s] (ELEMENTLOAD) with Function[%s] (\'dir\') does not match Options (\'dimension\') ***' % (lTag,fTag))

            #Check if TimeSerie file can be opened
            if 'file' in Entities['Functions'][fTag]['attributes']:
                LOAD = Entities['Loads'][lTag]['attributes']['type'].upper()
                filename = Entities['Functions'][fTag]['attributes']['file']
                if LOAD == 'GENERALWAVE':
                    #Gets the DRM Nodes
                    cond = False
                    eTag = Entities['Loads'][lTag]['attributes']['list']
                    nTag = set()
                    for k in eTag:
                        nlist = Entities['Elements'][k]['conn']
                        for n in nlist:
                            nTag.add(n)
                    #Check files can be opened
                    for k in nTag:
                        fname = filename.replace("$", str(k))
                        #Tries the path given by user
                        if tryOpenfile(fname):
                            #Tries a global path with respect to the main file
                            filepath = Options['path'] + '/' + fname
                            if tryOpenfile(filepath):
                                print('   *** ELEMENTLOAD (%s) file=\'%s\' in Function[%s] for Node[%s] could not be opened ***' % (LOAD,fname,fTag,k))
                            else:
                                cond = True
                    if cond:
                        Entities['Functions'][fTag]['attributes']['file'] = Options['path'] + '/' + filename
                elif LOAD == 'PLANEWAVE':
                    #Tries the path given by user
                    if tryOpenfile(filename):
                        #Tries a global path with respect to the main file
                        filepath = Options['path'] + '/' + Entities['Functions'][fTag]['attributes']['file']
                        if tryOpenfile(filepath):
                            print('   *** ELEMENTLOAD (%s) file=\'%s\' in Function[%s] could not be opened ***' % (LOAD,filename,fTag))
                        else:
                            filename = filepath
                            Entities['Functions'][fTag]['attributes']['file'] = filepath
                    #Opens the given file
                    with open(filename, "r") as fileHandler:
                        lines = fileHandler.readlines()
                        nDims = Options['dimension']
                        #Gets the number of DRM nodes
                        line  = list(filter(None, lines[0].strip().split())) 
                        nNode = int(line[2])
                        #Gets the DRM Nodes
                        eTag = Entities['Loads'][lTag]['attributes']['list']
                        allTag = set()
                        for k in eTag:
                            nlist = Entities['Elements'][k]['conn']
                            for n in nlist:
                                allTag.add(n)
                        #Gets the DRM node Tags
                        m = 0
                        nTags = np.empty(shape=(nNode,), dtype=int)
                        for k in range(1, nNode+1):
                            line = list(filter(None, lines[k].strip().split()))
                            nTags[m] = int(line[0])
                            m += 1
                        #Gets the the most distant coordinate
                        xmin = np.empty(shape=(nNode,nDims))
                        for k in range(nNode):
                            xmin[k] = Entities['Nodes'][nTags[k]]['coords']
                        Entities['Functions'][fTag]['attributes']['xmin'] = xmin.min(axis=0)

                        undefined = allTag.difference(nTags)
                        if undefined:
                            print('   *** ELEMENTLOAD (%s) in file=\'%s\' not all DRM nodes have been specified ***' % (LOAD,filename))
                elif LOAD == 'BODY':
                    #Tries the path given by user
                    if tryOpenfile(filename):
                        #Tries a global path with respect to the main file
                        filepath = Options['path'] + '/' + Entities['Functions'][fTag]['attributes']['file']
                        if tryOpenfile(filepath):
                            print('   *** ELEMENTLOAD (%s) file=\'%s\' in Function[%s] could not be opened ***' % (LOAD,filename,fTag))
                        else:
                            Entities['Functions'][fTag]['attributes']['file'] = filepath
                elif LOAD == 'SURFACE':
                    #Tries the path given by user
                    if tryOpenfile(filename):
                        #Tries a global path with respect to the main file
                        filepath = Options['path'] + '/' + Entities['Functions'][fTag]['attributes']['file']
                        if tryOpenfile(filepath):
                            print('   *** ELEMENTLOAD (%s) file=\'%s\' in Function[%s] could not be opened ***' % (LOAD,filename,fTag))
                        else:
                            Entities['Functions'][fTag]['attributes']['file'] = filepath
        elif Name == 'SUPPORTMOTION':
            nTag = Entities['Loads'][lTag]['attributes']['list']
            #Check if TimeSerie file can be opened
            for n in nTag:
                if 'file' in Entities['Supports'][n]:
                    filenames = Entities['Supports'][n]['file']
                    for ftag, filepath in enumerate(filenames):
                        #Tries the path given by user
                        if tryOpenfile(filepath):
                            #Tries a global path with respect to the main file
                            filename = Options['path'] + '/' + filepath
                            if tryOpenfile(filename):
                                print('   *** SUPPORTMOTION file=\'%s\' in Supports[%s] could not be opened ***' % (filepath,ftag))
                            else:
                                Entities['Supports'][n]['file'][ftag] = filename

    #[7] Check all attributes in DAMPING are defined in ENTITIES
    dlist = list(Entities['Elements'].keys())
    if not Entities['Dampings']:
        Entities['Dampings'][1] = {'name': 'FREE', 'attributes': {'list': eTags}}
    else:
        for dTag in Entities['Dampings']:
            if isinstance(Entities['Dampings'][dTag]['attributes']['list'], str):
                if Entities['Dampings'][dTag]['attributes']['list'].upper() == 'ALL':
                    Entities['Dampings'][dTag]['attributes']['list'] = eTags
                else:
                    print("   *** Attribute: 'list'=%d in Dampings[%s] is not recognized ***" % (dTag, Entities['Dampings'][dTag]['attributes']['list']))
            else:
                if Entities['Dampings'][dTag]['name'] == 'RAYLEIGH':
                    if 'am' not in Entities['Dampings'][dTag]['attributes']:
                        Entities['Dampings'][dTag]['attributes']['am'] = 0.0
                    if 'ak' not in Entities['Dampings'][dTag]['attributes']:
                        Entities['Dampings'][dTag]['attributes']['ak'] = 0.0
                elif Entities['Dampings'][dTag]['name'] == 'CAUGHEY':
                    Entities['Dampings'][dTag]['name'] = 'FREE'
                    print("   *** CAUGHEY in Dampings[%s] is not implemented yet ***" % dTag)
                elif Entities['Dampings'][dTag]['name'] == 'CAPPED':
                    Entities['Dampings'][dTag]['name'] = 'FREE'
                    print("   *** CAPPED in Dampings[%s] is not implemented yet ***" % dTag)
            #Finds elements without damping 
            daux  = dlist
            dlist = list(set(daux).difference(Entities['Dampings'][dTag]['attributes']['list']))

        #Creates a new free damping with the elements without damping
        if dlist:
            dTag = 1 + max(list( Entities['Dampings'].keys()))
            Entities['Dampings'][dTag] =  {'name': 'FREE', 'list': dlist}

    #[8] Check all attributes in RECORDERS are defined in ENTITIES
    for rTag in Entities['Recorders']:
        if 'list' in Entities['Recorders'][rTag]:
            if isinstance(Entities['Recorders'][rTag]['list'], str):
                if Entities['Recorders'][rTag]['name'] == 'NODE':
                    Entities['Recorders'][rTag]['list'] = nTags
                elif Entities['Recorders'][rTag]['name'] == 'SECTION':
                    Entities['Recorders'][rTag]['list'] = eTags
                elif Entities['Recorders'][rTag]['name'] == 'ELEMENT':
                    Entities['Recorders'][rTag]['list'] = eTags
        if 'response' in Entities['Recorders'][rTag]:
            if Entities['Recorders'][rTag]['response'] == 'REACTION':
                #TODO: Get all nodes that are fixed
                Entities['Recorders'][rTag]['list'] = [] 
        if Entities['Recorders'][rTag]['name'] == 'PARAVIEW':
            dirName = Options['path'] + '/' + 'Paraview'
            if not os.path.exists(dirName):
                os.mkdir(dirName)

    #[9] Check all attributes in SOLVER are defined in ENTITIES
    for sTag in Entities['Solvers']:
        if Entities['Solvers'][sTag]['name'] == 'PETSC':
            if Options['allocation'] == 'NO':
                print('   *** Solver[%s] uses PETSC (parallel) and memory allocation has not being computed ***' % sTag)
        elif Entities['Solvers'][sTag]['name'] == 'MUMPS':
            if Options['nparts'] == 1:
                print('   *** Solver[%s] uses MUMPS (parallel) for number of partition %d, we recommend using EIGEN (serial) ***' % (sTag,Options['nparts']))
        elif Entities['Solvers'][sTag]['name'] == 'EIGEN':
            if Options['nparts'] != 1:
                print('   *** Solver[%s] uses EIGEN (serial) and number of partition is %d (parallel) ***' % (sTag,Options['nparts']))

    #[10] Check all attributes in SIMULATION are defined in ENTITIES
    for sTag in Entities['Simulations']:
        if Entities['Simulations'][sTag]['attributes']['analysis'] not in Entities['Analyses']:
            print('   *** Simulation[%s] has no defined analysis  ***' % sTag)
        if Entities['Simulations'][sTag]['attributes']['algorithm'] not in Entities['Algorithms']:
            print('   *** Simulation[%s] has no defined algorithm  ***' % sTag)
        if Entities['Simulations'][sTag]['attributes']['integrator'] not in Entities['Integrators']:
            print('   *** Simulation[%s] has no defined integrator  ***' % sTag)
        if Entities['Simulations'][sTag]['attributes']['solver'] not in Entities['Solvers']:
            print('   *** Simulation[%s] has no defined solver ***' % sTag)
        if Entities['Simulations'][sTag]['combo'] not in Entities['Combinations']:
            print('   *** Simulation[%s] has no defined combination ***' % sTag)
           
    print(' Done checking!\n')

#Functions to be run when SeismoVLAB is imported
printHeader()

setFilePath()