#!/usr/bin/env python3
__author__ = "Achim Stein"
__version__ = "1.7"
__email__ = "achim.stein@ling.uni-stuttgart.de"
__status__ = "31.12.23"
__license__ = "GPL"

import sys
import argparse, pickle, re
import os
import fileinput
import datetime
from xmlrpc.client import boolean
import subprocess   # for system commands, here: tree-tagger
from collections import defaultdict   #  make dictionaries with initialised keys (avoids KeyError)
from itertools import count
import csv
# for pseudo lemmatisation:
import difflib
from Levenshtein import distance, ratio
import unicodedata

# global variables 
jointLex = defaultdict(str)   # option -l   Lexicon for TreeTagger training
openclass = defaultdict(str)   # openclass list
lemmaCode = 'l'     # default lemma markup in psd file, for @l=
triple = []

def get_arguments():
    parser = argparse.ArgumentParser(
        prog = "penntools.py",
        description =  '''
Converts Penn tree structures to 1 word per line format, for further processing.
- If Penn terminal nodes contain lemmas appended with @l=, they will be printed, else 'NA'.
- standard output is 3 tab-delimited columns (word-pos-lemma), with special codes wrapped in XML codes
  - use -c to change number of output columns
3 temporary files are written:
  - tmp-penntools-nodes   numbered words
  - tmp-penntools-tagme   words only (input to tagger)
  - tmp-<psd file>        copy of psd file with numbered terminal nodes, e.g. (pos word)#123 

Example:
- Extract words (terminal nodes) from Penn psd file:
    > "%(prog)s -c 1 FILE.psd > 1100-roland-mcvf.tagged
- Run tagger (any tagger, output needs to be one word per line, tab-delimited  (word-pos-lemma), e.g.
    > cut -f2 tmp-penntools-nodes | cmd/my-rnn.sh > tmp-tagged
- Join node number file with tagger output.
    > paste tmp-penntools-nodes tmp-rnn-tagged |cut -f1,3- > tmp-penntools-merge 
  This will create 4 columns, e.g.: #14	ad VERcjg avoir
- Merge annotation with psd file 
    > penntools.py -m tmp-penntools-merge tmp-penntools-FILE.psd
''',
        formatter_class = argparse.RawTextHelpFormatter   # allows triple quoting for multiple-line text
        )
    parser.add_argument(
        "file_name",
        help = "input data, table with tab delimiters")
    parser.add_argument(
        '-c', '--columns', default = 3, type = str,
        help='output columns: 1 2 3')
    parser.add_argument(
        '-l', '--lexicon', default = "", type = str,
        help='write lexicon to file (TreeTagger format)')
    parser.add_argument(
        '-L', '--lemma_code', default = "l", type = str,
        help='define the code used for lemmas in psd annotation (e.g. "l" for @l=')
    parser.add_argument(
        '-m', '--merge', default = "", type = str,
        help='reads annotation (3 column) and "tmp-penntools-nodes" and merges with psd file' )
    parser.add_argument(
        '--clean_lemmas', default = "", type = str,
        help='reads MED lemma list in HTML format and adds lemmas to tree-tagger annotated psd file' )
    parser.add_argument(
        '-p', '--plaeme', action='store_true',
        help='process PLAEME corpus with form-lemma')
    parser.add_argument(
        '-r', '--repair', action='store_true',
        help='repair some inconsistencies in the files (e.g. lemmatisation)')
    parser.add_argument(
        '-t', '--temp', action='store_true',
        help='compare tag lemma annotations in table')
    parser.add_argument(
        '--triples', default = ".*", type = str,
        help='write a file with tag triples or word_tag triples if tag matches argument')

    args = parser.parse_args()
    return args


def read_file(file_name):    # TODO: update this function: move pd.read_csv from main to here
    try:
        with open(file_name, "r", encoding='utf8', newline='') as inp:
            return inp.read()
    except FileNotFoundError:
        print("file not found", file_name)
        quit()

def main():
    args = get_arguments()   # get command line options
    if args.merge != '':   # -m
        mergeAnnotation()
        sys.exit('mergeAnnotation finished')
    if args.clean_lemmas != '':   # -p
        cleanLemmas()
        sys.exit('finished')
    if args.repair:   # -r
        repair()
        sys.exit('repair finished')
    if args.lexicon != '':   # initialise the output files
        with open(args.lexicon, 'a') as out:
            out.write("")
            out.close()
    if args.temp:   # call temporary function
        content = read_file(args.file_name)
        sentences = content.split('\n')
        tempFunction(sentences)
        quit()
    tmp = open('tmp-penntools-' + args.file_name, 'w')   # copy of psd with numbered terminal nodes (words)
    nodes = open('tmp-penntools-nodes', 'w')   # store node numbers of terminal nodes
    tagme = open('tmp-penntools-tagme', 'w')   # store the words to be tagged - parrallel to node numbers
    if args.triples != '':                    # option --triples
        tripleFile = open('tmp-penntools-triples', 'w')   # store the words to be tagged - parrallel to node numbers
        reTripleTag = re.compile(args.triples)
        triplet_counts = {}
    print('<text file="' + cleanXML(args.file_name) + '">')
    content = read_file(args.file_name)
    sentences = content.split('\n\n')
    sNr = 0
    conllNr = 0  # word numbering for CoNLL
    code = id = ''
    inCorpus = False
    wCount = count(0)   # counter for words
    for s in sentences:
        triple = [] # option --triples
        sNr += 1
        conllNr = 0  # reset
        if sNr % 100 == 0:  # display progress
            percent = int(sNr / len(sentences) * 100)
            sys.stderr.write(" processed: " + str(percent) + '%' + '\r')
        # add incremental number after each terminal node and write copy of psd file with node numbers
        rePennWord = re.compile(r'\((?P<inKlammern>(?P<tag>[^\)\(]+) (?P<word>[^\)\(]+))\)')
        rePennWordNum = re.compile(r'\((?P<inKlammern>(?P<tag>[^\)\(]+) (?P<word>[^\)\(]+))\)(?P<wNr>#\d+)')
        sNum = re.sub(rePennWord, lambda x: x.group(0) + '#' + str(next(wCount)), s)
        tmp.write(sNum + '\n\n')
        # special cases (non-sentences)
        if re.search(r'^\( \(CODE ([^\)\(]+)\)', s):  # no sentence, meta-textual markup (CODE ...)
            m = re.search(r'\(CODE ([^\)\(]+)\)', s)
            code = cleanXML(m.group(1))
            print('<div code="' + code + '"/>')
            continue
        elif (not re.search(r'\)\)', s)):  # no bracket structure, ignore
            continue
        elif re.search(r'MIRABILES', s):  # bug: structure without ID in CMMANDEV
            continue
        elif (not re.search(r'\(ID ([^\)\(]+)\)', s)):
            if inCorpus:  # if processing has started
                sys.stderr.write(">>>>> WARNING: ID not found in record " + str(sNr) + " of file " + args.file_name + '\n' + s)
                #sys.exit("Error")
        # sentences: get ID 
        else:
            matches = re.search(r'\(ID ([^\)\(]+)\)', s)
            id = matches.group(1)
            inCorpus = True
        # process terminal nodes in copy with terminal numbers
        if args.columns == "c":
            print('#%s ' % id)
        else:
            print('<s id="' + id + '">', sep='')
        for (terminal, tag, word, wNr) in re.findall(rePennWordNum, sNum):
            conllNr += 1
            word = re.sub(r'\$', '', word)
            word = re.sub(r'<slash>', '/', word)
            if not re.match(r'(NPR|NUM)', tag):
                word = word.lower()   # lines without lower:  99077 me-fullex
            tag = processTag(tag)
            lemma = ''
            lemmaCode = 'l'
            if args.lemma_code:
                lemmaCode = args.lemma_code
            reLemma = re.compile('@' + lemmaCode + '=')
            if re.match(r'ID', tag) or re.match(r'\*|0', word):
                if not args.columns == "c":
                    print('<div ignore="' + cleanXML(word) + '"/>', sep='')
            elif re.match(r'LINEBREAK', tag) and not args.columns == "c":  # in PLAEME: line breaks
                print('<div code="LINEBREAK"/>')
            elif re.match(r'CNJCTR', tag) and not args.columns == "c":  # in PLAEME: contracted forms
                print('<div code="CNJCTR"/>')
            elif re.search(reLemma, word):   # if lemma annotation exists
                (word, lemma) = processLemma(word, lemmaCode)
                if args.plaeme and re.search(r'(.*?)-(.*)', word):   # -p  split word-lemma in PLAEME
                    m = re.search(r'(.*?)-(.*)', word)
                    word = m.group(1)
                    # lemma = lemma + "@p=" + m.group(2)    # don't add the lemma if we have a @l= lemma
                addToLex(word, tag, lemma, wNr, conllNr)
                if not re.search(r'[<{]', word):
                    tagme.write('%s\n' % word)
                    nodes.write('%s\t%s\n' % (wNr, word))
            else:
                lemma = 'NA'
                if args.plaeme and re.search(r'(.*?)-(.*)', word):   # -p  split word-lemma in PLAEME
                    m = re.search(r'(.*?)-(.*)', word)
                    word = m.group(1)
                    lemma = "@p=" + m.group(2)
                if not(args.columns == "c" and tag == "CODE"):
                    addToLex(word, tag, lemma, wNr, conllNr)
                # for Tagging, write only pure words (no codes)
                if not re.search(r'[<{]', word):
                    tagme.write('%s\n' % word)
                    nodes.write('%s\t%s\n' % (wNr, word))
            # store info for triplet list if word is not empty or a code
            if args.triples and not (re.match(r'ID', tag) or re.match(r'\*|0', word)):
                triple.append(f'{word}\t{tag}')
                if len(triple) > 3:
                    triple.pop(0)
                # keep only triples with MD in the middle
                if len(triple) == 3 and re.search(reTripleTag, triple[1]):
                    #period = re.sub(r'_.*', '', args.file_name)
                    textID = re.sub(r',.*', '', id)
                    triple.append(textID)
                    printTriple = '\t'.join(triple)
                    tripleFile.write(printTriple + '\n')
                    countTriple = '___'.join(triple) # tuple(triple)
                    # increment and avoid KeyError by setting to default 0
                    triplet_counts[countTriple] = triplet_counts.setdefault(countTriple, 0) + 1  # Increment the count

    # write triples       
    if args.triples:
        for triplet in triplet_counts.keys():
            splitTriplet = re.sub('___', '\t', triplet)
#            tripleFile.write(f"{triplet_counts[triplet]}\t{splitTriplet}\n")

        nodes.write('\n')    # node list needs an empty line
        tagme.write('\n')    # tagme list needs an empty line
        print('</s>\n')      # sentences need to be separated by empty line for RNN tagger
    print('</text>')
    sys.stderr.write('\n')    # progress counter
    nodes.close()
    tagme.close()

    # text processed, now write lexicon
    if args.lexicon:  
        writeLexicon()



#----------------------------------------------------------------------
# functions
#----------------------------------------------------------------------

# -m merge annotation with psd file
def mergeAnnotation():
    args = get_arguments()   # get command line options
    merge = open(args.merge, 'r')
    nrAnnot = {}  # build a dictionary with tagger annotation 
    for row in csv.reader(merge, delimiter ='\t', quoting=csv.QUOTE_NONE):
        if any(row):   # avoid errors with empty lines
            if len(row) == 4:
                if re.search(r'[<>\(\)]', row[3]):
                    row[3] = 'NA'  #row[1]  # repair brackets inserted by RNN tagger: use word instead of lemma
                nrAnnot[row[0]] = '@rl=' + row[3] + '@rt=' + row[2]
            else:
                sys.stderr.write(">>>>> mergeAnnotation: fields missing in annotation:" + '\t'.join(row) + '\n')
    merge.close()
    psd = open(args.file_name, 'r')   # read copy of psd file with numbered words (=terminal nodes)
    wholeText = psd.read()
    mtch = re.compile(r'\)(#\d+)')   # match the inserted word numbers
    wholeText = re.sub(r'\)(#\d+)', lambda x: getAnnotation(nrAnnot, x.group(1))+')', wholeText)
    print(wholeText)   # TODO: better write to a file 
    return()
        
def OLD_pceec():
    args = get_arguments()   # get command line options
    # read tagger lexicon
    pceec = open(args.pceec, 'r')
    formLemma = {}  # build a dictionary with tagger lexicon 
    for row in csv.reader(pceec, delimiter ='\t', quoting=csv.QUOTE_NONE):
        if any(row):   # avoid errors with empty lines
            if len(row) == 3:
                if re.search(r'^V', row[1]):
                    formLemma[row[0]] = row[2]
    sys.stderr.write(str(len(formLemma.keys())) + " forms stored in lexicon\n")
    pceec.close()
    # read MED lemmas
    med = open(args.med_lemmas, 'r')   # read copy of psd file with numbered words (=terminal nodes)
    #med_html = med.read()
    medIDLemma = dict()
    for line in med.readlines():
        reEntry = re.compile('<a href=.MED_(\d+)\.html.>\[(.*?),')  # <a href='MED_53772.html'>[yarmen, v.]</a>
        if re.search(reEntry, line):
            mtch = re.search(reEntry, line)
            MEDid = mtch.group(1)
            MEDlemmaOrig = mtch.group(2)
            clean_lemma = unicodedata.normalize("NFKD", MEDlemmaOrig).encode("ascii", "ignore")
            clean_lemma = clean_lemma.decode("ascii")  # strip diacritics
            medIDLemma[clean_lemma] = MEDid
#            print(">>>> %s %s %s" % (MEDid, MEDlemmaOrig, clean_lemma))
    sys.stderr.write(str(len(medIDLemma.keys())) + " forms stored in MED lexicon\n")
    # read corpus filep
    psd = open(args.file_name, 'r')   # read copy of psd file with numbered words (=terminal nodes)
    wholeText = psd.read()
    mtch = re.compile(r'\)(#\d+)')   # match the inserted word numbers
    # TODO: clean the added annotation
    wholeText = re.sub(r'@rl=', '@l=', wholeText)
    # process unlemmatized word
    thisWord = 'dismissed'
    closestLemmas = []
    letter =  thisWord.split()[0][0] # first letter of word
    print('FIRST=' + letter)
    letter = re.compile('^' + letter)
    # define word list that is searched for matching forms
    words = formLemma.keys()  # tagger lexicon
    filteredWords = [i for i in words if letter.match(i)]
    # match form against other word forms
    closestWords = difflib.get_close_matches(thisWord, filteredWords)
    print(closestWords)
    for w in closestWords:
        print('%s: %s %s. Lemma: %s' % (thisWord, w, ratio(thisWord, w), formLemma[w]))
        lemma = re.sub('@.*', '', formLemma[w])
        closestLemmas.append(lemma)
    closestLemmas = [i for i in medIDLemma.keys() if letter.match(i)]
    closestLemmas = difflib.get_close_matches(thisWord, closestLemmas)
    # match a modified form against MED lemmas
    reFlex = re.compile('(.*)e[^aeiouy]')  # get 'stem' of inflected form
    mtch = re.search(reFlex, thisWord)
    if mtch:
        thisWord = mtch.group(1) + 'en'
        closestLemmas = difflib.get_close_matches(thisWord, closestLemmas)
    print('With pseudo stem :' + str(closestLemmas))
    last = 0
    best = ''
    for w in closestLemmas:
        levenshtein_ratio = ratio(thisWord, w)
        print('%s: %s %s. ' % (thisWord, w, levenshtein_ratio))
        if levenshtein_ratio > last:
            best = w
            last = levenshtein_ratio
    print('best match: %s %s %s' % (best, last, round(last, 2)))
#    print(wholeText)   # TODO: better write to a file 
    return()

def cleanLemmas():
    args = get_arguments()   # get command line options
    # read MED lemmas and store in dictionary
    med = open(args.clean_lemmas, 'r')   # read MED lemma list (HTML)
    medIDLemma = dict()
    medSimpleClean = dict()
    for line in med.readlines():    # Example line: <a href='MED_53772.html'>[yarmen, v.]</a>
        reEntry = re.compile('<a href=.MED_(\d+)\.html.>\[(.*?),')
        if re.search(reEntry, line):
            mtch = re.search(reEntry, line)
            MEDid = mtch.group(1)
            MEDlemmaOrig = mtch.group(2)
            clean_lemma = unicodedata.normalize("NFKD", MEDlemmaOrig).encode("ascii", "ignore")
            clean_lemma = clean_lemma.decode("ascii")  # strip diacritics
            clean_lemma = re.sub('\(', '[', clean_lemma) # change parentheses (for CorpusSearch)
            clean_lemma = re.sub('\)', ']', clean_lemma)
            clean_lemma = re.sub('_', '', clean_lemma)  # rare, e.g. vouch safe
            # conflate some graphical variants
            simpleLemma = meSimplify(clean_lemma)
            medSimpleClean[simpleLemma] = clean_lemma  # new dict for simplified->original lemma
            medIDLemma[clean_lemma] = MEDid
    sys.stderr.write(str(len(medIDLemma.keys())) + " forms stored in MED lexicon\n")
    # read corpus file
    psd = open(args.file_name, 'r')   # read copy of psd file with numbered words (=terminal nodes)
    wholeText = psd.read()
    # TODO: clean the added annotation
    wholeText = re.sub(r'@rl=', '@l=', wholeText) # correct lemma code
    wholeText = re.sub(r'@rt=.*?\)', ')', wholeText) # delete tag annotation
    reNoLemma = re.compile('\((?P<all>V\S+ (?P<word>.*?)@l=NA)\)')  # e.g. (VAN dismissed@rl=NA@rt=VAN)
    # replace missing verb lemmas
    while re.search(reNoLemma, wholeText):
        mtch = re.search(reNoLemma, wholeText)
        #thisTag = mtch.group(1)
        thisWord = mtch.group('word')
        best = bestLemma (thisWord, medSimpleClean)  # medIDLemma
        newLemma = best[0]
        prob = str(round(best[1], 2))
        newLemma = medSimpleClean.get(newLemma, 'NA')  # avoid dict key error
        medID = medIDLemma.get(newLemma, '0')
        etym = 'nonfrench'
        if isFrench(int(medID)):  # TODO add Levenshtein ratio
            etym = 'french'
        new = re.sub('@l=NA', '@l='+newLemma+'@m='+medID+'@e='+etym+'@p='+prob, mtch.group('all'))
        wholeText = wholeText.replace(mtch.group('all'), new) # insert new lemma
    wholeText = re.sub(r'@l=NA', "", wholeText) # delete non-verbal unknown lemmas
    # further cleaning
    wholeText = re.sub('l=na@m=na|', "", wholeText)
    wholeText = re.sub(r' (.*?)\|(.[^=].*?@.*?\))', ' \g<1>@l=\g<2>', wholeText)
    wholeText = re.sub(r' ([^\)]+@l=[^\)]+@a=[^\)]+)\|[^\)]+\)', ' \g<1>)', wholeText)
# day@l=day@a=inanimate|day@a=inanimate++
    wholeText = re.sub(r'\((AUTHOR.*?)@l=.*?\)', "(\g<1>)", wholeText) # delete non-verbal unknown lemmas
    print(wholeText)   # TODO: better write to a file 
    return()

# simplify ME forms
def meSimplify (clean_lemma):
    simpleLemma = re.sub('y([aeiou])', 'g\g<1>', clean_lemma)  # e.g. foryeten > forgeten
    simpleLemma = re.sub('y', 'i', clean_lemma)
    return(simpleLemma)

def bestLemma (thisWord, medIDLemma):
    closestLemmas = []
    reLetter = re.compile('.')
    letter =  thisWord.split()[0][0] # first letter of word
    if re.search(r'\w+', letter):
        reLetter = re.compile('^' + letter)
    thisWord = meSimplify(thisWord)
    #sys.stderr.write('Simplified -> %s' % (thisWord))
    # make list of MED verbs with matching first letter
    closestLemmas = [i for i in medIDLemma.keys() if reLetter.match(i)]
    closestLemmas = difflib.get_close_matches(thisWord, closestLemmas)  # get 3 best matches
    # if possible convert word to pseudo lemma before matching it against MED lemmas
    reFlex = re.compile('(.*)(e|est|eth|ed)$')  # get 'stem' of inflected form
    mtch = re.search(reFlex, thisWord)
    if mtch:
        thisWord = mtch.group(1) + 'en' # make pseudo lemma
        closestLemmas = difflib.get_close_matches(thisWord, closestLemmas)
    #sys.stderr.write('closest lemmas :' + str(closestLemmas))
    # keep the best of 3 candidates using Levenshtein similarity
    levenshtein_ratio = last = 0
    best = ''
    for w in closestLemmas:
        levenshtein_ratio = ratio(thisWord, w)
        #print('%s: %s %s. ' % (thisWord, w, levenshtein_ratio))
        if levenshtein_ratio > last:
            best = w
            last = levenshtein_ratio
    #print('best match: %s %s %s' % (best, last, round(last, 2)))
    return([best, levenshtein_ratio])

def isFrench(medID):
        frenchID = [ 17, 22, 22, 28, 36, 38, 58, 78, 108, 122, 135,\
		137, 141, 154, 181, 192, 195, 201, 209, 220, 221, 240, 245,\
		256, 263, 282, 286, 305, 324, 330, 340, 345, 357, 365, 368,\
		371, 377, 380, 383, 395, 397, 398, 402, 405, 406, 408, 483,\
		498, 513, 537, 551, 559, 570, 573, 578, 599, 605, 608, 646,\
		652, 652, 655, 679, 680, 691, 692, 697, 701, 702, 704, 705,\
		721, 725, 728, 728, 729, 741, 795, 843, 846, 859, 880, 886,\
		896, 896, 905, 931, 943, 954, 957, 959, 960, 999, 1010, 1015,\
		1117, 1132, 1164, 1165, 1170, 1171, 1182, 1182, 1194, 1234,\
		1237, 1250, 1252, 1291, 1316, 1334, 1336, 1352, 1370, 1390,\
		1394, 1405, 1405, 1410, 1419, 1419, 1420, 1422, 1424, 1424,\
		1445, 1460, 1463, 1476, 1480, 1493, 1494, 1571, 1593, 1629,\
		1645, 1645, 1646, 1676, 1685, 1692, 1696, 1705, 1722, 1724,\
		1794, 1798, 1799, 1801, 1807, 1816, 1820, 1852, 1879, 1882,\
		1889, 1903, 1912, 1917, 1919, 1920, 1923, 1925, 1928, 1932,\
		1943, 1945, 1950, 1964, 1976, 1976, 1982, 1992, 1996, 2004,\
		2034, 2051, 2063, 2063, 2063, 2067, 2073, 2114, 2168, 2179,\
		2184, 2191, 2214, 2220, 2253, 2264, 2298, 2316, 2325, 2329,\
		2355, 2431, 2431, 2433, 2444, 2475, 2525, 2525, 2547, 2550,\
		2556, 2561, 2572, 2573, 2578, 2586, 2588, 2618, 2628, 2639,\
		2640, 2645, 2660, 2662, 2664, 2666, 2691, 2697, 2699, 2717,\
		2743, 2766, 2808, 2810, 2814, 2816, 2877, 2880, 2884, 2896,\
		2913, 2933, 2938, 2938, 2948, 2980, 2980, 2980, 3016, 3057,\
		3082, 3094, 3099, 3101, 3110, 3116, 3119, 3141, 3144, 3147,\
		3164, 3166, 3174, 3176, 3178, 3188, 3201, 3208, 3211, 3212,\
		3220, 3230, 3239, 3384, 3441, 3458, 3463, 3506, 3526, 3583,\
		3604, 3639, 3664, 3708, 3756, 3765, 3765, 3782, 3783, 3959,\
		4228, 4667, 4962, 4990, 5082, 5104, 5120, 5124, 5127, 5139,\
		5159, 5359, 5394, 5544, 5595, 5716, 5731, 5732, 5769, 5770,\
		5791, 5792, 5851, 5862, 5900, 5901, 6024, 6100, 6122, 6175,\
		6175, 6210, 6281, 6290, 6351, 6355, 6419, 6420, 6440, 6442,\
		6518, 6631, 6755, 6811, 6843, 6847, 6901, 6912, 6975, 6992,\
		7036, 7040, 7143, 7155, 7168, 7173, 7196, 7256, 7256, 7278,\
		7307, 7311, 7337, 7376, 7383, 7455, 7527, 7538, 7701, 7755,\
		7759, 7763, 7769, 7786, 7806, 7840, 7882, 8039, 8089, 8104,\
		8125, 8194, 8285, 8293, 8293, 8293, 8302, 8302, 8362, 8383,\
		8383, 8424, 8466, 8497, 8518, 8533, 8558, 8566, 8586, 8592,\
		8598, 8600, 8626, 8656, 8665, 8670, 8681, 8692, 8700, 8702,\
		8710, 8715, 8720, 8726, 8747, 8753, 8763, 8766, 8770, 8775,\
		8806, 8809, 8812, 8816, 8857, 8860, 8862, 8886, 8898, 8907,\
		8913, 8915, 8928, 8945, 8972, 8977, 8998, 9038, 9074, 9160,\
		9183, 9243, 9301, 9303, 9340, 9345, 9348, 9364, 9379, 9387,\
		9389, 9404, 9404, 9414, 9434, 9437, 9461, 9465, 9477, 9501,\
		9514, 9539, 9547, 9565, 9583, 9595, 9612, 9612, 9612, 9616,\
		9632, 9636, 9636, 9661, 9767, 9812, 9830, 9843, 9897, 9915,\
		9931, 9963, 9982, 9991, 10006, 10007, 10010, 10016, 10020,\
		10028, 10029, 10029, 10039, 10043, 10085, 10099, 10112, 10113,\
		10127, 10194, 10228, 10239, 10254, 10281, 10304, 10306, 10316,\
		10343, 10393, 10403, 10473, 10504, 10514, 10533, 10577, 10587,\
		10594, 10599, 10601, 10619, 10622, 10630, 10649, 10654, 10673,\
		10692, 10704, 10711, 10724, 10725, 10727, 10731, 10759, 10760,\
		10775, 10777, 10780, 10784, 10788, 10793, 10805, 10823, 10828,\
		10837, 10849, 10857, 10863, 10874, 10879, 10880, 10890, 10893,\
		10957, 10984, 10989, 11012, 11021, 11058, 11078, 11095, 11096,\
		11123, 11137, 11149, 11158, 11158, 11168, 11173, 11178, 11180,\
		11185, 11187, 11190, 11202, 11228, 11253, 11268, 11278, 11282,\
		11282, 11291, 11297, 11312, 11344, 11344, 11346, 11363, 11370,\
		11387, 11399, 11415, 11433, 11434, 11444, 11481, 11486, 11492,\
		11537, 11568, 11577, 11577, 11581, 11586, 11589, 11593, 11646,\
		11647, 11680, 11708, 11753, 11756, 11758, 11761, 11764, 11775,\
		11778, 11780, 11793, 11793, 11799, 11801, 11810, 11814, 11822,\
		11825, 11831, 11831, 11837, 11847, 11851, 11860, 11868, 11888,\
		11891, 11895, 11905, 11914, 11914, 11918, 11924, 11949, 11952,\
		11954, 11966, 11971, 11973, 11976, 11976, 11985, 11991, 11998,\
		12004, 12007, 12009, 12009, 12012, 12023, 12029, 12029, 12035,\
		12042, 12047, 12055, 12055, 12060, 12060, 12062, 12066, 12070,\
		12095, 12101, 12122, 12127, 12142, 12146, 12152, 12171, 12174,\
		12184, 12187, 12187, 12192, 12215, 12234, 12238, 12243, 12257,\
		12273, 12291, 12325, 12352, 12399, 12434, 12448, 12490, 12529,\
		12592, 12602, 12735, 12759, 12835, 12976, 13103, 13277, 13334,\
		13336, 13339, 13342, 13346, 13349, 13351, 13356, 13359, 13367,\
		13374, 13374, 13378, 13384, 13386, 13391, 13401, 13433, 13436,\
		13438, 13476, 13478, 13479, 13481, 13488, 13491, 13494, 13497,\
		13506, 13527, 13531, 13535, 13545, 13546, 13549, 13553, 13554,\
		13556, 13563, 13569, 13586, 13595, 13595, 13605, 13612, 13620,\
		13623, 13630, 13636, 13642, 13645, 13656, 13657, 13675, 13683,\
		13700, 13700, 13704, 13704, 13706, 13710, 13714, 13720, 13728,\
		13754, 13757, 13760, 13764, 13765, 13769, 13770, 13773, 13779,\
		13783, 13787, 13791, 13799, 13802, 13812, 13831, 13837, 13839,\
		13840, 13848, 13854, 13855, 13858, 13861, 13867, 13871, 13876,\
		13877, 13878, 13886, 13888, 13890, 13896, 13903, 13910, 13921,\
		13925, 13926, 13930, 13933, 13937, 13944, 13949, 13953, 13954,\
		13958, 13975, 13976, 13977, 13978, 13982, 13983, 13988, 13992,\
		14000, 14004, 14013, 14017, 14022, 14024, 14025, 14026, 14033,\
		14046, 14066, 14071, 14072, 14089, 14098, 14098, 14102, 14110,\
		14115, 14125, 14128, 14132, 14132, 14144, 14150, 14154, 14159,\
		14162, 14165, 14170, 14174, 14175, 14178, 14179, 14191, 14191,\
		14197, 14198, 14199, 14330, 14373, 14422, 14430, 14446, 14448,\
		14453, 14464, 14472, 14472, 14475, 14496, 14529, 14612, 14666,\
		14676, 14761, 14773, 14784, 14798, 14801, 14814, 14824, 14841,\
		14841, 14855, 14863, 14877, 14879, 14887, 14892, 14909, 14958,\
		14964, 14964, 14968, 14970, 14975, 14979, 14987, 14999, 15045,\
		15058, 15078, 15111, 15144, 15170, 15171, 15208, 15213, 15233,\
		15244, 15264, 15278, 15295, 15362, 15389, 15389, 15407, 15413,\
		15444, 15463, 15470, 15558, 15659, 15710, 15711, 15714, 15801,\
		15801, 15869, 15876, 15888, 15956, 15984, 16013, 16028, 16194,\
		16202, 16202, 16222, 16395, 16507, 16511, 16515, 16547, 16653,\
		16654, 16655, 16694, 16705, 16706, 16711, 16946, 16995, 17005,\
		17022, 17028, 17051, 17086, 17097, 17105, 17284, 17308, 17312,\
		17438, 17457, 17458, 17469, 17480, 17521, 17575, 17598, 17598,\
		17650, 17716, 17717, 17718, 17740, 17804, 17815, 17817, 17822,\
		17838, 17843, 17868, 17872, 17922, 17948, 17949, 17967, 17977,\
		17987, 17989, 17992, 18031, 18056, 18234, 18244, 18266, 18289,\
		18340, 18364, 18446, 18498, 18514, 18525, 18558, 18652, 18666,\
		18672, 18760, 18841, 18852, 18939, 19096, 19106, 19157, 19169,\
		19179, 19257, 19274, 19316, 19329, 19437, 19555, 19632, 19665,\
		19670, 19743, 19821, 19915, 19988, 20066, 20144, 20151, 20152,\
		20156, 20445, 20445, 20459, 20552, 20686, 20900, 21140, 21153,\
		21282, 21304, 21354, 21544, 21562, 21984, 22010, 22022, 22150,\
		22152, 22209, 22216, 22221, 22239, 22251, 22252, 22264, 22271,\
		22326, 22587, 22678, 22679, 22766, 22867, 22897, 22937, 23037,\
		23121, 23174, 23412, 23421, 23507, 23774, 23797, 23881, 23881,\
		23893, 23894, 23914, 23933, 23949, 23957, 24045, 24057, 24063,\
		24512, 24636, 24639, 24645, 24680, 24693, 24709, 24720, 24851,\
		24855, 25256, 25618, 25720, 25852, 25917, 26121, 26126, 26191,\
		26324, 26357, 26426, 26434, 26443, 26486, 26520, 26534, 26538,\
		26548, 26568, 26670, 26714, 26725, 26753, 26768, 26871, 26882,\
		26883, 26914, 26922, 26982, 27014, 27022, 27022, 27045, 27045,\
		27090, 27117, 27170, 27188, 27188, 27246, 27276, 27302, 27330,\
		27406, 27477, 27528, 27606, 27621, 27630, 27638, 27638, 27699,\
		27803, 27803, 27823, 27834, 27842, 27886, 27984, 28000, 28197,\
		28203, 28237, 28276, 28419, 28433, 28452, 28468, 28495, 28503,\
		28503, 28506, 28539, 28548, 28557, 28610, 28644, 28696, 28698,\
		28706, 28712, 28807, 28823, 28861, 28890, 28901, 28912, 28929,\
		28935, 28943, 28957, 28988, 28989, 29015, 29126, 29658, 29676,\
		29698, 29801, 29813, 29886, 29902, 30015, 30056, 30062, 30080,\
		30101, 30111, 30131, 30135, 30144, 30172, 30176, 30287, 30299,\
		30475, 30532, 30537, 30537, 30753, 30771, 30776, 30785, 30818,\
		30879, 30985, 31086, 31093, 31097, 31105, 31328, 31354, 31523,\
		31888, 32148, 32178, 32218, 32219, 32316, 32363, 32372, 32375,\
		32413, 32424, 32444, 32448, 32477, 32501, 32556, 32604, 32633,\
		32672, 32734, 32738, 32752, 32777, 32814, 32860, 32894, 32910,\
		32910, 32913, 32920, 32940, 32954, 32955, 32966, 32968, 32984,\
		32991, 33000, 33029, 33032, 33035, 33049, 33075, 33089, 33126,\
		33142, 33145, 33156, 33170, 33187, 33406, 33430, 33513, 33580,\
		33581, 33587, 33604, 33639, 33667, 33713, 33720, 33737, 33759,\
		33770, 33791, 33804, 33815, 33825, 33867, 33876, 33877, 33927,\
		33985, 33990, 34030, 34044, 34106, 34123, 34129, 34131, 34158,\
		34206, 34250, 34267, 34278, 34282, 34319, 34336, 34366, 34386,\
		34390, 34392, 34400, 34401, 34413, 34444, 34453, 34457, 34467,\
		34489, 34504, 34513, 34522, 34546, 34560, 34574, 34581, 34583,\
		34650, 34687, 34725, 34730, 34752, 34765, 34770, 34783, 34806,\
		34809, 34819, 34827, 34832, 34851, 34868, 34871, 34880, 34886,\
		34904, 34906, 34917, 34919, 34921, 34926, 34949, 34952, 34974,\
		34992, 35001, 35009, 35009, 35015, 35070, 35082, 35137, 35152,\
		35184, 35217, 35223, 35231, 35238, 35243, 35255, 35260, 35268,\
		35274, 35278, 35278, 35280, 35302, 35324, 35324, 35334, 35359,\
		35401, 35414, 35464, 35471, 35557, 35579, 35583, 35682, 35686,\
		35723, 35768, 35804, 35806, 35807, 35808, 35849, 35856, 35874,\
		35925, 35930, 35943, 35943, 35949, 35958, 35981, 35995, 36010,\
		36015, 36020, 36028, 36048, 36076, 36085, 36099, 36104, 36106,\
		36114, 36114, 36125, 36131, 36140, 36146, 36155, 36158, 36160,\
		36174, 36176, 36182, 36183, 36186, 36189, 36192, 36196, 36199,\
		36202, 36207, 36212, 36212, 36224, 36233, 36240, 36253, 36259,\
		36279, 36287, 36302, 36348, 36350, 36353, 36356, 36361, 36371,\
		36379, 36388, 36392, 36404, 36415, 36421, 36424, 36426, 36431,\
		36440, 36448, 36460, 36474, 36484, 36489, 36502, 36511, 36518,\
		36524, 36524, 36527, 36539, 36544, 36558, 36579, 36584, 36586,\
		36589, 36589, 36592, 36618, 36625, 36635, 36638, 36644, 36649,\
		36658, 36658, 36663, 36665, 36673, 36673, 36677, 36683, 36694,\
		36717, 36725, 36742, 36747, 36751, 36763, 36770, 36774, 36782,\
		36788, 36811, 36813, 36817, 36819, 36825, 36841, 36845, 36853,\
		36858, 36862, 36865, 36870, 36876, 36887, 36895, 36912, 36923,\
		36929, 36939, 36944, 36957, 36964, 36969, 36970, 36978, 36982,\
		36985, 36993, 36996, 36996, 37035, 37036, 37042, 37047, 37051,\
		37058, 37062, 37075, 37080, 37091, 37103, 37107, 37108, 37111,\
		37111, 37119, 37122, 37125, 37125, 37134, 37137, 37137, 37143,\
		37146, 37147, 37163, 37173, 37179, 37191, 37197, 37199, 37202,\
		37207, 37213, 37249, 37252, 37254, 37260, 37261, 37262, 37266,\
		37287, 37319, 37321, 37331, 37332, 37344, 37360, 37367, 37371,\
		37377, 37378, 37380, 37385, 37386, 37392, 37396, 37402, 37467,\
		37468, 37489, 37544, 37562, 37564, 37577, 37612, 37671, 37700,\
		37766, 37766, 37771, 37772, 37802, 37803, 37803, 37889, 37985,\
		37996, 38016, 38017, 38019, 38041, 38066, 38143, 38146, 38217,\
		38222, 38277, 38277, 38360, 38550, 38550, 38601, 38622, 38642,\
		38656, 38705, 38748, 38762, 38768, 38865, 38865, 38885, 38892,\
		38909, 38921, 38945, 38962, 39003, 39058, 39199, 39214, 39243,\
		39284, 39337, 39338, 39447, 39449, 39461, 39496, 39526, 39545,\
		39583, 39584, 39609, 39659, 39701, 40226, 40262, 40262, 40276,\
		40326, 40343, 40408, 40664, 40693, 40716, 40915, 40940, 41302,\
		41348, 41351, 41360, 41364, 41387, 41387, 41413, 41422, 41427,\
		41494, 41496, 41502, 41641, 41754, 41764, 41812, 41824, 41833,\
		41848, 41848, 41853, 41929, 41941, 41951, 41990, 42019, 42041,\
		42094, 42104, 42185, 42193, 42238, 42309, 42368, 42464, 42474,\
		42485, 42491, 42542, 42585, 42701, 42737, 42738, 42765, 42778,\
		42887, 43020, 43039, 43063, 43069, 43124, 43190, 43207, 43221,\
		43247, 43248, 43323, 43365, 43438, 43449, 43450, 43518, 43531,\
		43550, 43555, 43560, 43568, 43570, 43587, 43609, 43613, 43621,\
		43621, 43625, 43653, 43663, 43668, 43672, 43749, 43812, 43824,\
		43825, 43832, 43837, 43846, 43855, 43866, 43868, 43870, 43874,\
		43888, 43899, 43899, 43903, 43915, 43927, 43929, 43933, 43942,\
		43946, 43954, 43958, 43971, 44001, 44041, 44371, 44397, 44434,\
		44509, 44544, 44583, 44587, 44622, 44661, 44666, 44672, 44726,\
		44756, 44783, 44841, 44886, 44898, 44908, 44925, 44972, 45716,\
		45762, 45786, 45978, 46208, 46247, 46371, 46462, 46559, 46559,\
		46559, 46661, 46685, 46693, 46702, 46708, 46762, 46795, 46805,\
		46807, 46823, 46845, 46852, 46867, 46877, 46895, 46913, 46928,\
		46932, 46953, 46973, 46989, 47049, 47079, 47134, 47180, 47229,\
		47273, 47294, 47335, 47339, 47356, 48893, 50630, 50642, 50648,\
		50692, 50702, 50716, 50723, 50749, 50781, 50788, 50863, 50880,\
		50895, 50895, 50895, 50896, 50911, 50954, 50977, 50993, 51000,\
		51006, 51018, 51065, 51068, 51082, 51109, 51124, 51154, 51154,\
		51162, 51208, 51230, 51250, 51282, 51295, 51295, 51305, 51354,\
		51389, 51417, 51417, 51425, 51516, 51534, 51607, 51709, 51729,\
		51777, 51777, 51804, 51811, 51811, 51823, 51859, 52061, 52239,\
		52314, 52319, 52845, 52848, 52887, 333941 ]
        if medID in frenchID:
                return True
        else:
                return False
    
# called by lambda function, returns string which replaces the terminal number 
def getAnnotation(nrAnnot, key):
    if key in nrAnnot.keys():
        return(nrAnnot[key])
    else:
        return ''

# -l  write lexicon in TreeTagger format
def writeLexicon():
    with open(args.lexicon, 'w') as out:
        sys.stderr.write("--- Output lexicon file: " + args.lexicon + '\n')
        for word in sorted(jointLex.keys()):
            out.write(word)
            for item in jointLex[word]:   # for all tag-lemma dictionaries...
                for tag in item.keys():   # ...write tag and joined lemma list
                    out.write('\t' + tag + '\t' + '|'.join(item[tag]))
            out.write('\n')
        out.write("</s>\tSENT\tSENT\n")   # train-tree-tagger requires SENT in the lexicon
    sys.stderr.write("--- Suggested tags for open class file (train-tree-tagger):")
    for tag in sorted(openclass.keys()):
        sys.stderr.write(tag + '\n')
    quit()

# write lexicon file (-l) and one-word-per-line file (stdout)
def addToLex(word, tag, lemma, wNr, conllNr):     #  process tags
    args = get_arguments()   # get command line options
    if word == "" or tag == "" or lemma == "":
        sys.stderr.write(">>>>> addToLex WARNING: skipping incomplete line: word,tag,lemma = " + ','.join([word, tag, lemma]) + "wNr="+wNr+'\n')
    else:
        # print corpus in word-tag-lemma format
        if args.columns == 1:
            print(word)
        elif args.columns == 2:
            print(word, tag, sep="\t")
        elif args.columns == "c":  # CoNLL-U
            print("%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s" % (conllNr, word, "_", "_", tag, "_", "0", "root", "_", wNr))
        else:
            print(word, tag, lemma, sep="\t")
        if re.match('^(ADJ|ADV|V|N.*|NUM|VB|VB[A-Z])', tag):
            openclass[tag] = ''   # store tags for openclass tags (required for training)
        # store lexicon as nested dictionaries with lists as values
        # word : [ tag1 : [ lemma1, lemma 2 ...], tag2 : [lemma1, lemma2, ...] ...]
        if not word in jointLex:    # new word
            jointLex[word] = [ {tag: [lemma] } ]   # value = list of dicts. Each dict has key=tag and values= list of lemmas
        else:
            tagExists = False
            for item in jointLex[word]:  # for all tag:lemma dictionaries
                if tag in item:  # if the tag exists
                    tagExists = True
                    if lemma != 'NA':   # don't append NA to existing lemmas
                        if lemma in item[tag]:
                            pass  #  known tag and lemma: nothing done
                        else:
                            item[tag].append(lemma)   # known tag, new lemma: append the lemma
            if tagExists == False:
                jointLex[word].append( {tag: [lemma]} )  # new tag: append dict tag: list of lemmas
    return()

def processTag(value):     #  process tags
    value = re.sub(r'[0-9].*', '', value)   #  VB21
    value = re.sub(r'\+.*', '', value)
    value = re.sub(r'-.*?', '', value)
    value = re.sub(r' ', '', value)  # some bugs in PCMEP
    #value = re.sub(r'\$', '', value)     # $ marks possessives (genitives)
    return(value)

def processLemma(value, lemmaCode):     #  process strings starting with @l=
    value = replaceAmalgamated(value)    # temporary replace in amalgamated forms: l@  @en
    word = ''
    lemma = 'NA'
    reWordLemma = re.compile('(?P<word>.*?)(@.*)?' + '@' + lemmaCode + '=(?P<lemma>[^@]*)')
    if re.search(reWordLemma, value):
        m = re.search(reWordLemma, value)
        word = m['word']
        lemma = m['lemma']
    if re.search(r'\|', lemma):  # simplify ambiguous lemma strings
        lemmas = lemma.split('|')
        lemmas = list(map(lambda x: re.sub(r'_.*', '', x), lemmas))   #  strip _<tag> from each element
        if 'NA' in lemmas:
            lemmas.remove('NA')   # remove NA from list
        lemmas = set(lemmas)  # unique: reduce list to types
        lemma = '_'.join(lemmas)
    # deal with BASICS annotation added to Middle English
    if re.search(r'@a=([^@]*)', value):
        anim = re.search(r'@a=([^@]*)', value).group(1)
        lemma = lemma + '@a=' + anim
    if re.search(r'@m=([^@]*)', value):
        med = re.search(r'@m=([^@]*)', value).group(1)
        lemma = lemma + '@m=' + med
    if re.search(r'@e=([^@]*)', value):
        etym = re.search(r'@e=([^@]*)', value).group(1)
        lemma = lemma + '@e=' + etym
    word = cleanTaggerWord(word)
    return(word, lemma)

def cleanXML(value):     #  clean XML values
    value = re.sub(r'[<>\"]', r'', value)        # quick & dirty tokenization
    return(value)

# replace @ in amalgamated forms, e.g. el (< en+le) coded as e@ @l
def replaceAmalgamated(s):
    s = re.sub(r'@([@\)])', r'++\1', s)   # e@ before ')' or added annotation ('@')
    s = re.sub(r'^@', r'++', s)   # @l at beginning of word
    return(s)

def cleanTaggerWord(s):
    s = re.sub(r'\+\+', '', s)
    s = re.sub(r'[=_]', '', s)
    return(s)

def tempFunction(sentences):     #  clean XML values
    # compare lemmas / tags from RNN (rl, rt) and LGeRM (ll, lt)
    tagErrors = defaultdict(int)
    wordErrors = defaultdict(int)
    for s in sentences:
        cols = s.split('\t')
        if len(cols) == 6:
            w = cols[0]  # Penn word
            pt = cols[1]  # Penn tag
            rl = cols[2]
            ll = cols[3]
            rt = cols[4].lower()
            lt = cols[5].lower()
            if re.search(r'PON', pt) == None and rt != lt:
                cols.append('0')
                key = rt+'-'+lt
                tagErrors[key] += 1
                if re.search(r'<.*>', w) == None and re.search(r'CODE', pt) == None:
                    key = w+'_'+pt
                    if re.search(r'NUM', pt):
                        key = '##Numeral##_'+'*NUM*'
                    if re.search(r'NPR', pt):
                        key = '##ProperNoun##_'+ pt
                    wordErrors[key] += 1
            else:
                cols.append('1')
        print('\t'.join(cols))
    tErr = open('tmp-error-tags.csv', 'w')
    sys.stderr.write('x=============== writing tag errors\n')
    tErr.write('RNN-LGeRM'+'\t'+ 'Freq' +'\n')
    for k in sorted(tagErrors.keys()):
        tErr.write(k+'\t'+str(tagErrors[k])+'\n')
    tErr.close()
    wErr = open('tmp-error-words.csv', 'w')
    sys.stderr.write('x=============== writing word errors\n')
    wErr.write('word_PennTag'+'\t'+ 'Freq' +'\n')
    for w in sorted(wordErrors.keys()):
        wErr.write(w+'\t'+str(wordErrors[w])+'\n')
    wErr.close()
    return()

# -r repair:  add missing annotation @l= @t= 
def repair():
    args = get_arguments()   # get command line options
    psdFile = read_file(args.file_name)
    sentences = psdFile.split('\n\n')
    reWord = re.compile('\(([A-Z][^ \)]*? [^ \)]+?)\)', re.DOTALL)
    reLGERM = re.compile('.*@l=.*@t=.*')  # lemma and tag
    reRNN = re.compile('.*@rl=.*@rt=.*')  # lemma and tag
    addL = 0
    addR = 0
    for s in sentences:
        for w in re.findall(reWord, s):
            if (not re.match(reLGERM, w)) and re.match(reRNN, w):
                wNew = re.sub(r'@rl=', '@l=NA@t=NA@rl=', w)    # add missing lgerm annotation
                s = re.sub(re.escape(w), wNew, s)  # escape needed: there may be special chars in the strings
                addL += 1
            elif re.match(reLGERM, w) and (not re.match(reRNN, w)):
                wNew = w + '@rl=NA@rt=NA'    # add missing RNN annotation
                s = re.sub(re.escape(w), wNew, s)
                addR += 1
            else:
                pass
        print(s + '\n')
    sys.stderr.write('  added annotations: LGerM=%s  RNN=%s\n' % (addL, addR) )
    return()
    

# -------------------------------------------------------
# don't delete the call of main
if __name__ == "__main__":
    main()
