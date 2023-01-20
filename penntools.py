#!/usr/bin/env python3
__author__ = "Achim Stein"
__version__ = "1.4"
__email__ = "achim.stein@ling.uni-stuttgart.de"
__status__ = "running"
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

# global variables 
jointLex = defaultdict(str)   # option -l   Lexicon for TreeTagger training
openclass = defaultdict(str)   # openclass list
lemmaCode = 'l'     # default lemma markup in psd file, for @l=

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
        '-c', '--columns', default = 3, type = int,
        help='output columns: 1 2 3')
    parser.add_argument(
        '-l', '--lexicon', default = "", type = str,
        help='write lexicon to file (TreeTagger format')
    parser.add_argument(
        '-L', '--lemma_code', default = "l", type = str,
        help='define the code used for lemmas in psd annotation (e.g. "l" for @l=')
    parser.add_argument(
        '-m', '--merge', default = "", type = str,
        help='reads annotation (3 column) and "tmp-penntools-nodes" and merges with psd file' )
    parser.add_argument(
        '-p', '--plaeme', action='store_true',
        help='process PLAEME corpus with form-lemma')
    parser.add_argument(
        '-r', '--repair', action='store_true',
        help='repair some inconsistencies in the files (e.g. lemmatisation)')
    parser.add_argument(
        '-t', '--temp', action='store_true',
        help='compare tag lemmma annotations in table')
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
    print('<text file="' + cleanXML(args.file_name) + '">')
    content = read_file(args.file_name)
    sentences = content.split('\n\n')
    sNr = 0
    code = id = ''
    inCorpus = False
    wCount = count(0)   # counter for words
    for s in sentences:
        sNr += 1
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
                sys.stderr.write(">>>>> ID not found in record " + str(sNr) + " of file " + args.file_name + '\n' + s)
                sys.exit("Error")
        # sentences: get ID 
        else:
            matches = re.search(r'\(ID ([^\)\(]+)\)', s)
            id = matches.group(1)
            inCorpus = True
        # process terminal nodes in copy with terminal numbers
        print('<s id="' + id + '">', sep='')
        for (terminal, tag, word, wNr) in re.findall(rePennWordNum, sNum):
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
                print('<div ignore="' + cleanXML(word) + '"/>', sep='')
            elif re.match(r'LINEBREAK', tag):  # in PLAEME: line breaks
                print('<div code="LINEBREAK"/>')
            elif re.match(r'CNJCTR', tag):  # in PLAEME: contracted forms
                print('<div code="CNJCTR"/>')
            elif re.search(reLemma, word):   # if lemma annotation exists
                (word, lemma) = processLemma(word, lemmaCode)
                if args.plaeme and re.search(r'(.*?)-(.*)', word):   # -p  split word-lemma in PLAEME
                    m = re.search(r'(.*?)-(.*)', word)
                    word = m.group(1)
                    # lemma = lemma + "@p=" + m.group(2)    # don't add the lemma if we have a @l= lemma
                addToLex(word, tag, lemma, wNr)
                if not re.search(r'[<{]', word):
                    tagme.write('%s\n' % word)
                    nodes.write('%s\t%s\n' % (wNr, word))
            else:
                lemma = 'NA'
                if args.plaeme and re.search(r'(.*?)-(.*)', word):   # -p  split word-lemma in PLAEME
                    m = re.search(r'(.*?)-(.*)', word)
                    word = m.group(1)
                    lemma = "@p=" + m.group(2)
                addToLex(word, tag, lemma, wNr)
                # for Tagging, write only pure words (no codes)
                if not re.search(r'[<{]', word):
                    tagme.write('%s\n' % word)
                    nodes.write('%s\t%s\n' % (wNr, word))
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
                    row[3] = row[1]  # repair brackets inserted by RNN tagger: use word instead of lemma
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
def addToLex(word, tag, lemma, wNr):     #  process tags
    args = get_arguments()   # get command line options
    if word == "" or tag == "" or lemma == "":
        sys.stderr.write(">>>>> addToLex WARNING: skipping incomplete line: word,tag,lemma = " + ','.join([word, tag, lemma]) + "wNr="+wNr+'\n')
    else:
        # print corpus in word-tag-lemma format
        if args.columns == 1:
            print(word)
        elif args.columns == 2:
            print(word, tag, sep="\t")
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
#        if wordErrors[w] > 10:
        wErr.write(w+'\t'+str(wordErrors[w])+'\n')
    wErr.close()
    return()

# -r repair
def repair():
    args = get_arguments()   # get command line options
    psdFile = read_file(args.file_name)
    sentences = psdFile.split('\n\n')
    sNr = 0
    code = id = ''
    wCount = count(0)   # counter for words
    reWord = re.compile('\(([A-Z][^ \)]*? [^ \)]+?)\)', re.DOTALL)
    reLGERM = re.compile('.*@l=[^@]+\w+@t=[^@]+.*')  # lemma and tag
    reRNN = re.compile('.*\w+@lr=[^@]+\w+@tr=[^@]+.*')  # lemma and tag
    reLGERM = re.compile('.*@l=.*@t=.*')  # lemma and tag
    reRNN = re.compile('.*@rl=.*@rt=.*')  # lemma and tag
    # first parse: get maximum annotation string
    addL = 0
    addR = 0
    # second parse: add missing annotation @l= @t= 
    for s in sentences:
        sNr += 1
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
