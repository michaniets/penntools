#!/usr/bin/python3

__author__ = "Achim Stein"
__version__ = "1.3"
__email__ = "achim.stein@ling.uni-stuttgart.de"
__status__ = "13.1.23"
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
#import csv

# global variables
htmlServer = "http://141.58.164.21/basics"  # julienas (IP Nr reduces table file size)
lastFile = ''  # HTML text file
logFile = 'penn-coding.log'   # not used in this version
htmlHead = '''<!DOCTYPE html>
<html>
  <meta http-equiv="Content-type" content="text/html; charset=utf-8" />
  <head>
    <title>PENN CORPUS</title>
    <style>
      .parse p {
        font-family: monospace;/* Web-safe typewriter-like font */
        overflow: hidden;/* Ensures the content is not revealed until the animation */
        border-left: .17em solid blue;/* The typewriter cursor */
        white-space: nowrap;/* Keeps the content on a single line */
        margin: 0 auto;/* Gives that scrolling effect as the typing happens */
        letter-spacing: 0em;/* Adjust as needed */
      }
      .coding {
        background:gray; color:yellow;
      }
    </style>
  </head>
  <body>
'''
htmlFoot='''  </body>
</html>
'''
htmlSource = '''
<hr>
<font color="red">
<a href="https://www.ling.upenn.edu/hist-corpora/other-corpora.html">Penn Historical Corpora</a>.<br>
Depending on the corpus, license restrictions may apply when re-using the data.<br>
Coding and HTML conversion by A. Stein (University of Stutgart)<br>
&nbsp;&nbsp;French lemmatization by A. Stein (University of Stutgart) using RNN (Schmid 2019; LMU München) and BFM training data (A. Lavrentev, IHRIM, ENS de Lyon)<br>
&nbsp;&nbsp;English lemmatization by BASICS/SILPAC project members (University of Mannheim)<br>
%s %s (%s)<br>
<a href="index.html">List of files</a>
</font>
''' % (os.path.basename(__file__), __version__, str(datetime.date.today()))
corpusName = 'MCVF-PPCHF'  # default
htmlDir = "mcvf-ppchf"

def main(args):
  global htmlDir
  errorNr = 0   # for log file
  sNr = 0  # counter for sentences
  cNr = 0  # counter for CODING
  rowNr = 0  # counter for output rows
  headerPrinted = None  # control printing of column header
  featHeader = []  # column header
  htmlFile = '' # html output file 
  suffix = dict()  # html file suffix
  id = ''  # printable ID
  pid = ''  # unique ID for match
  sprint = ''  # printable example
  sparsed = ''  # parsed example (bracket structure)
  lCode = args.lemma_code  # 'l'  # default lemma code  @l=
  reVerbPOS = args.verb_pos  # extract info for these POS
  with open(args.cod_file, 'r') as file:  # , newline=''
    all = file.read() #file.split('\n\n')
    sentences = all.split('/~*')
  with open(logFile, 'w') as log:
    log.write('')  # init log file
  if args.corpus:
    corpusName = args.corpus  # parametrize for different Penn corpora
    if re.search(r'(me|english|ppcme|pcmep|plaeme)', corpusName, re.IGNORECASE):
      htmlDir = "penn-html"
      reVerbPOS = '^(NEG\+)?(VA|VB|MD|DA|DO|HA|HV|BE).*'
      reCoordPOS='V.*',   # TODO setting it here doesn't seem to work. Use -c
    elif re.search(r'(pceec)', corpusName, re.IGNORECASE):
      htmlDir = "pceec"
      reVerbPOS = '^(VB|MD|DA|DO|HA|HV).*'
      reCoordPOS='V.*',
    elif re.search(r'(mcvf)', corpusName, re.IGNORECASE):
      htmlDir = "mcvf-ppchf"
    else:
      sys.exit('  error option --corpus: unknown corpus')
  if args.coord_pos:
    reCoordPOS = args.coord_pos  # count coordination for these POS
  if args.html:
    os.makedirs(htmlDir, exist_ok=True)
    debug("Directory '% s' created\n" % htmlDir)
    with open(htmlDir+'/index.html', 'w') as file:
        file.write(htmlHead + '\n\n')
        file.write(htmlSource + '\n\n')
  sys.stderr.write('Processing %s sentences.\n' % (str(len(sentences))))
  sys.stderr.write('   Retrieving verb nodes matching "%s" \n' % (reVerbPOS))
  sys.stderr.write('   Counting coordinated verbs matching "%s" \n' % (reCoordPOS))
  for s in sentences:
    sNr += 1
    if sNr % 100 == 0:  # display progress
        percent = int(sNr / len(sentences) * 100)
        sys.stderr.write(" processed: " + str(percent) + '%' + '\r')
    sprint = sparse = ''
    # match print example and parsed structure
    reSent = re.compile('\*~/.*\(ID (.*?)\)', re.DOTALL)      # DOTALL  . match also \n
    if not re.search(reSent, s):   # . match also \n
      continue  # skip records without ID code
    else:
      s = replaceAmalgamated(s)   #  MCVF: deal with '@' in amalgamations, e.g. el (< en+le) coded as e@ @l
      id = re.search(reSent, s).group(1)
      sp = s.split(r'*~/')
      sprint = formatReadable(sp[0], lCode)
      sparsed = sp[1]
      sparsed = re.sub(r'\t', '        ', sparsed)
      sparsed = re.sub(r'^\n', '', sparsed)  # strip blank lines
      sparsed = re.sub(r'\n\n', '\n', sparsed)  # strip blank lines
      codingNodes = getCodings(sparsed)
      # for each coded IP (key = index) browse terminal nodes for CODING features and verbal nodes
      reCoding = re.compile('CODING-(?P<ip>.*?) (?P<features>ipHead=(?P<head>.*?):.*?)')
      reLem = re.compile(r'(.*?)@' + lCode + '=([^@]+)') # lemma in annotation
      for key in sorted(codingNodes.keys()):   # for all coding node IPs
        beginLine = len(re.findall(r'\n', sparsed[1:key], re.DOTALL)) + 1 # get line number for this CODING
        # set column values for this coding IP
        pid = id + '_' + str(beginLine)   # TODO: key char offset is not practical: get line number
        htmlFile = openHTML(id, suffix, sprint, sparsed, 'urlFile')
        url = '=HYPERLINK("%s/%s#%s"; "WWW")' % (htmlServer, htmlFile, id)
        url2 = '=HYPERLINK("http://localhost/%s#%s"; "LOC")' % (htmlFile, id)
        coord = 0
        featRow = addFeatures = []   # empty feature list
        nodes = codingNodes[key]   # list of terminal nodes under coding IP
        # set coord to > 0 if more than one verbal (modal) node
        coord = hitsInList(str(reCoordPOS), nodes) - 1   # histInList takes string (not re)
        # for all terminal nodes 
        for n in nodes:   
          pos, form = n.split(' ')    # original Penn pos and form
          if re.search(r'CODING-(.*)', pos):   # get the features from the CODING node
            ipType = re.search(r'CODING-(.*)', pos).group(1)
            debug(' >------- features: ' +str(key) + ': ' + form)
            if not headerPrinted:      # define the column header, if not present
              print(makeFeatureHeader(form))  # form are attribute:value pairs of CODING
              headerPrinted = True
            for f in form.split(':'):
              val = re.sub(r'.*=', '', f)
              addFeatures.append(val)
            continue
          if re.search(reVerbPOS, pos):   # get lexical info from these verbal nodes
            vpos = re.sub(r'[-=]\d+', '', pos)   # strip indices
            vlemma = 'NA'
            vform = form  # default, if no annotation was added
            if re.search(reLem, form):
              vlemma = re.search(reLem, form).group(2)
              vform = re.search(reLem, form).group(1)
              vform = re.sub(r'@.*', '', form)
            featRow = [pid, url, url2, ipType, vpos, vform, vlemma, str(coord)] + addFeatures
            rowNr+=1
            print('%s\t%s' % (str(rowNr), '\t'.join(featRow)))
    # print sentence as HTML
    if args.html:
      openHTML(id, suffix, sprint, sparsed, 'nil')
  # messages on exit
  sys.stderr.write(str(rowNr) + ' lines written\n')
  if args.html:
    sys.stderr.write('HTML files written to folder %s \n' % htmlDir)
    sys.stderr.write('Hint: Update HTML files on remote or local server:\n    rsync -zav --no-perms %s/ %s:/Library/WebServer/Documents/basics/%s\n    rsync -zav --no-perms %s/ /Library/WebServer/Documents/%s\n' % (htmlDir, htmlServer, htmlDir, htmlDir, htmlDir))


  if errorNr > 0:
    sys.stderr.write('  !!! %s error messages in %s\n' % (str(errorNr), logFile))
  log.close()
  with open(htmlDir+'/index.html', 'a') as file:
    file.write('\n</body>\n</html>\n')
    file.close()
  sys.exit(0)
  
#-------------------------------------------------------
# functions
#-------------------------------------------------------


# for all IP with CODING, returns dict of indexes of enclosing ( )
def getCodings(sparsed):
    pairs = findParens(sparsed)  # pairs of matching ( )
    codPairs = {}
    reCode = re.compile('\(IP[^ ]*? \(CODING', re.DOTALL)  #
    for ip in re.finditer(reCode, sparsed):
        beg = ip.start()
        end = pairs[ip.start()]
        debug(' index range of CODING IP: %s-%s %s ' % (beg, end, ip.group()))
        codPairs[beg] = end    # pairs of matching ( ) of IPs with coding
    # loop through coded IPs, most embedded one first (i.e. with lower end index)
    codingNodes = {}
    nodes = []
    while codPairs:
        beg = min(codPairs, key=codPairs.get)
        end = codPairs[beg]
        s = sparsed[beg:end]  # only the coding structure
        del codPairs[beg]   # remove this pair
        nodes = getNodes(s)   # get list of terminal nodes for this coding
        codingNodes[beg] = nodes
        sDel = re.sub(r'.', 'X', s)   # replace processed coding segments
        sparsed = sparsed.replace(s, sDel)
    return(codingNodes)

# in string, returns terminal nodes (called by getCodings)
def getNodes(s):
    nodes=[]
    reWord = re.compile('\((?P<node>[A-Z][^ \)]*? [^ \)]+?)\)', re.DOTALL)  # TODO verify update of this regex
    reVerb = re.compile('\((?P<node>(V|MD|EJ|AJ)[^ \)]+? [^ \)]+?)\)', re.DOTALL)  # TODO
    for w in re.findall(reWord, s):
        nodes.append(w)
    return(nodes)

# in string, finds matching ( ), returns dict of  begin:end  positions
def findParens(s):
    pairs = {}
    pstack = []
    for i, c in enumerate(s):
        if c == '(':
            pstack.append(i)
        elif c == ')':
            if len(pstack) == 0:
                raise IndexError("No matching closing parens at: " + str(i))
            pairs[pstack.pop()] = i
    if len(pstack) > 0:
        raise IndexError("No matching opening parens at: " + str(pstack.pop()))
    return pairs

# returns number of occurrences of str in list elements
def hitsInList(str, lst):
  r = re.compile(str)   
  l = [ s for s in lst if r.match(s) ]
  return(len(l))

# file names for HTML output, with increments to avoid huge files
def openHTML(id, suffix, sprint, sparsed, control):
  global lastFile   # use global var in this function
  htmlFile = re.sub(r'[\.,].*', '', id)
  if htmlFile == '':
    sys.exit('no file' + id)
  if htmlFile in suffix.keys():
    suffix[htmlFile] += 1
  else:
    suffix[htmlFile] = 1
  thisSuffix = suffix[htmlFile]//1000  # 1000 sentences ~ 1MB file size
  outFile = htmlDir + '/' + htmlFile + '-' + str(thisSuffix) + '.html'
  if control == 'urlFile':
    return(outFile)
  if outFile != lastFile:  # open a new HTML file
    if lastFile != '':
      htmlFooter(lastFile)  # write HTML footer for last file
    htmlHeader(outFile)  # write HTML header for new files
    # write index file for 'manual' access of HTML files
    with open(htmlDir+'/index.html', 'a') as file: 
      urlName = re.sub(r'.*/', '', outFile)
      indexName = re.sub(r'\.html', '', urlName)
      if re.search(r'(.*)-0', indexName):
        m = re.search(r'(.*)-0', indexName)
        file.write('<h3>%s</h3>\n' % m.group(1))  # list new file in HTML index file
      s = '<a href="%s">%s</a><br>\n' % (urlName, indexName)
      file.write(s)  # list new file in HTML index file
  writeHTML(outFile, id, sprint, sparsed)
  lastFile = outFile
  return()

# write HTML header for new files
def htmlHeader(htmlFile):
    global htmlHead
    title = re.sub(r'(.*/|\.html)', '', htmlFile)      # insert HTML title in html header
    htmlHead = re.sub(r'<title>(.*?)</title>', '<title>'+title+'</title>', htmlHead)
    with open(htmlFile, 'w') as file:
        file.write(htmlHead + '\n\n')
        file.write(htmlSource + '\n\n')
    return()

def htmlFooter(htmlFile):
    with open(htmlFile, 'a') as file:
        file.write(htmlFoot)
    file.close()
    return()

def writeHTML(htmlFile, id, sprint, sparsed):
    with open(htmlFile, 'a') as file:
        out = '\n<a name=\"%s\"></a><hr>\n<h3>%s</h3>\n%s<hr>\n\n<p><div class=\"parse\"><p>%s</em></p></div>\n' % (id, id, sprint, penn2html(sparsed))
#        file.write(penn2html(sparsed) + '\n\n')
        file.write(out + '\n\n')
    return()

def makeFeatureHeader(features):
        featHeader = ["nr", "textid", "URLwww", "URLlok", "ipType", "pos", "form", "lemma", "coord"]
        for f in features.split(':'):
          att = re.sub(r'=.*', '', f)
          featHeader.append(att)
        return('\t'.join(featHeader))

# strip annotation, return plain text
def formatReadable(X, lCode):
    tCode = 'rt'
    X = re.sub(r'\n+', ' ', X)
    X = re.sub(r' \(.*?\)', '', X)
    tokens = X.split(r' ')
    words = [re.sub(r'@[^=]+=.*', '', w) for w in tokens]
    p = re.compile('.*@' + lCode + '=([^@]+).*')  #.*@rl=
    lemmas = [re.sub(p, r'\1', w) for w in tokens]
    p = re.compile('.*@' + tCode + '=([^@]+).*')  #.*@rl=
    pos = [re.sub(p, r'\1', w) for w in tokens]
    lempos = []
    for i in range(0, len(lemmas)):
        lempos.append(lemmas[i]+'<sub><font color="gray">'+pos[i]+'</font></sub>')
    s = '<font color="blue">%s</font><br>\n%s<br>\n' % (' '.join(words), ' '.join(lempos))
    return(s)

# make HTML version of parsed structure
def penn2html(X):
    line = count(start=2)
    X = re.sub(r'^\n', '', X)
    X = re.sub(r'\n', '<br>\n', X)
    X = re.sub(r'<(nolem|unknown)>', 'NA', X)
    X = re.sub(r'\n( +)', lambda x: '\n'  + indent(x.group(0) ,line), X)  # indentation with dots
    X = re.sub(r'(\(CODING.*?\))', r'<span class="coding">\1</span>', X)
    X = re.sub(r'@[^=]+=.*?\)', ')', X)   # drop annotation
    X = re.sub(r'<(.*?)>\)', r'&lt;\1&gt;)', X)  # deal with < >
    X = re.sub(r'\((V.*?) (.*?)(@.*?)?\)', r'(<font color="magenta">\1</font> \2<i>\3</i>)', X)
    X = re.sub(r'\((MD.*?) (.*?)(@.*?)?\)', r'(<font color="blue">\1</font> \2<i>\3</i>)', X)
    X = re.sub(r'\(([AE]J.*?) (.*?)(@.*?)?\)', r'(<font color="green">\1</font> \2<i>\3</i>)', X)
    return(X)

# used by penn2html: returns HTMl-compatible indentation string
def indent(X, line):
    nr = next(line)
    shorten = len(str(nr))
    indent = str(nr) + (len(X)//2 - shorten) * '.'
    return(indent)

# option -D print debug messages
def debug(msg):
    if args.debug:
        sys.stderr.write('\n   DEBUG>>>'+msg+'<<<DEBUG\n')
    return()

# replace @ in amalgamated forms, e.g. el (< en+le) coded as e@ @l
def replaceAmalgamated(s):
    s = re.sub(r'@([@\)])', r'+\1', s)   # e@ before ')' or added annotation ('@')
    s = re.sub(r'(\n| )@', r'\1+', s)   # @l at beginning of word
    return(s)

###########################################################################
# main function
###########################################################################

if __name__ == "__main__":

   parser = argparse.ArgumentParser(description='Process output of CorpusSearch coding queries.')

   parser.add_argument('cod_file', type=str,
                       help='CorpusSearch cod file')
   parser.add_argument('-C', '--corpus', type=str, default='MCVF',
                       help='adapt to other Penn corpora: me=Middle English; pceec=PCEEC')
   parser.add_argument('-D', '--debug', action='store_true',
                       help='print debugging messges (stderr)')
   parser.add_argument('-H', '--html', action='store_true',
                       help='create HTML output')
   parser.add_argument('-l', '--lemma_code', type=str, default='l',
                       help='define lemma code')
   parser.add_argument('-c', '--coord_pos', type=str, default='(V.*|MD.*) ',
                       help='count these POS under IP to determine coordination')
   parser.add_argument('-v', '--verb_pos', type=str, default='^(V|MD|EJ|AJ).*',
                       help='for these POS (regex) retrieve info from terminal nodes')

   args = parser.parse_args()

   main(args)
