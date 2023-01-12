# penntools: annotation and coding queries for Penn historical corpora

## penntools.py

Converts Penn tree structures to 1 word per line format, for further processing.

- If Penn terminal nodes contain lemmas appended with @l=, they will be printed, else 'NA'.
- standard output is 3 tab-delimited columns (word-pos-lemma), with special codes wrapped in XML codes
  - use -c to change number of output columns
- 3 temporary files are written:
  - tmp-penntools-nodes   numbered words
  - tmp-penntools-tagme   words only (input to tagger)
  - tmp-&lt;psd file&gt;      copy of psd file with numbered terminal nodes, e.g. (pos word)#123 
	
### Use penntools.py for tagging psd files with penntools.sh

```penntools.sh <psd_file> <tagger_script>```

penntools.sh will:
- extract words (terminal nodes) from Penn psd file (penntools.py -c ...)
- run tagger on the extracted file (the script is configured for RNN Tagger)
- merge (unix _paste_) node number file with tagger output.
  This will create 4 columns, e.g.: #14	ad VERcjg avoir
- merge annotation with psd file (penntools.py -m ...)
- store output in a subfolder

## penn-coding.py

- Task: Extract tabular information about verbal argument structures.
- Method: CorpusSearch codin query + conversion to table
- Corpora: Penn historical copora

	- Old French: MCVF-PPCHF
    - Middle English: PPCME2, PLAEME, PCMEP
	- Early Modern English: PCEEC

- Status of Python script:

  - for MCVF-PPCHF: working, verified
  - for PCEEC: not tested
  - for Middle English: working, with Options '-C me -l l -c
    'V.*''. Verification needed. See versions and bugs below.

### MCVF-PPCHF

The original corpus distribution was further annotated using lemmatizers and taggers.
Latest version: RNN lemmatizer and Tagger (Schmid 2019).

#### Files

CorpusSearch (CS):

- mcvf-ppchf-coding.q
- mcvf-ppchf.def

Script

- penn-coding.py

#### Processing


```cat *.psd > all.psd    # concatenate to avoid arbitrary order of files```

```corpussearch.sh mcvf-ppchf-coding.q all.psd     # coding query```

```penn-coding.py -H -l rl mcvf-ppchf-coding.cod > mcvf-coding-patterns-20dez22.csv    # extract table```

```rsync -zav --no-perms mcvf-ppchf/ julienas:/Library/WebServer/Documents/basics/mcvf-ppchf    # corpus as HTML```



#### Annotation

The CS query is composed of several conditions.
For each condition, CS annotates an attribute-value pair to the specified node (IP*).

Our conditions target mainly verb complements, but also other features like active/passive, negation, clitics. 
The _else_ value (unmatched condition) is usually '0'.

Attributes fromt the CS query:

- ipHead: the pos tag of the verbal head under IP (verbal, modal, be, have, ...)
	- values: MODINF MOD BE HAVE IP verb
    - note: IP is mostly from clause coordination. 0 is mostly for
      small clauses (without verbal head).
- clit: number of clitics under IP
	- values: 0-3
- subj: subject realized as lexical, pronominal, quantifier, null, clitic
	- values: lex pro quant clit null trace ...
- dobj: direct object (NP-ACC) realized as lexical, pronominal, quantifier, null, clitic
	- values: lex pro quant clit trace ...
- iobj: indirect object (NP-DTV) realized as lexical, pronominal, quantifier, null, clitic
	- values: lex pro quant clit trace ...
- pobj: prepositional phrase realized as lexical, pronominal, quantifier, null, clitic
	- values: lex pro clit
- ipobj: IP complement
	- values: (the various types of IP-*) sub inf imp smc ppl abs other
	- note: 'inf' almost only with modal verbs; 'ppart' for auxiliary + participle; vp for direct speech, imperatives etc
- cpobj: CP complement
	- values: (the various types of CP-*) adv clf rel tht cmp deg frl car cp
	- note: 'inf' almost only with modal verbs; 'ppart' for auxiliary + participle; vp for direct speech, imperatives etc
- spc: [NOT FILLED] secondary predicates
- aux: auxiliary verb.  '-prefinal' if particple precedes the final verb (embedded under PARTP)
	- values: etre etreprefinal avoir avoirprefinal
- reflself: reflexive même (with pronominal referent). It is coded as an ADJP. Coding distinguishes under which argument it is embedded: subject, direct/indirect object, predicate
	- values: NPsbj NPacc NPdtv NPprn NP
- reflclit: clitic _se_
	- values: acc dtv rfl null
- neg: negation present
	- values: 0 1
- year: the date of each text, clumsily inserted by a matching the ID annotation


#### Conversion to table

Python script penn-coding.py converts CorpusSearch coded output (cod) to table (csv)

**Rows**

The script parses the syntactic structure of each sentence. It
identifies for each coded IPs the enclosing pair of parenthesis.

- processes all the coded IPs, starting with the most deeply embedded
one (based on the index of closing parenthesis)
- retrieves the terminal nodes (words, traces etc), selects verbal
terminal nodes (_V*, MD*, EJ*, AJ*_)
- For each verbal it prints one table row, combining
information from the added annotation (see list below) with the
features of the CODING (see list above).

**Columns**

The script creates the following columns, and adds the columns for the
attributes of the CorpusSearch query:

- nr: row
- textid: text code from ID plus '_line' for this CODING line
- URLwww: URL to jump into a HTML file (generated from psd file) on our server (password needed for first-time access)
- URLlok: same for local web server
- ipType: the full IP* node to which CODING is applied
- pos: verb part of speech (Penn annotation)
- form: verb form (Penn annotation)
- lemma: verb lemma (added annotation)
  - note: lemmas are attached to the verb form after '@'. Lemma code can be specified as option in Python script.
- coord: better 'coocurrence' of _x_ lexical or modal verbs under one IP. Each coordinated element has its own row
  - values: 0 (none = 1 verb), 1 (1 added verb), 2 (2 added verbs), ...
  - note: -1 occurs (rarely) when _avoir/estre_ occur as main verb,
    but with AJ/EJ tag. Also in rare cases of auxiliary coordination
    (_he is and was never called..._)


#### History

**Next:**


**Latest:**

Version 1.1 24.12.22: parsing based on parentheses (instead of indentation):

Coding query:

- added rule for -SPR as secondary predicate (ADJP-SPR)
- added NP-MSR to rule for dobj

Script:

- Parses syntactic structure based on parentheses.
- It doesn't retrieve information from deeper levels,
  for example participles embedded under VPP (typically when
  participle precedes the auxilary): 'NA' were printed for verb form
  and lemma. **ignore in quantitative studies**

Version 1.0 20.12.22: first Python implementation, based on Perl
mcvf-coding.pl

- extracts "CODING" based on indentation level.

### Middle English corpora

tested with these options:

```penn-coding.py -C me -H -l l temp.cod > temp.csv```

Corpus selection 'me' sets retrieved verbs to:
```^(NEG\+)?(VB|MD|DA|DO|HA|HV|BE).*"```

#### History

**Next:**

Bug: upenn-coding.pl retrieves more verbs than penn-coding.py. CHECK!

```awk -F'\t' '$3 ~ /V.*/' pcmep-perl.csv |wc -l
   26303
awk -F'\t' '$6 ~ /V.*/ ' pcmep.csv |wc -l
   25501 ```

Functions:

- include alternative Lemmas

**Latest:**

Version 1.2 24.12.22: first Python implementation, based on Perl upenn-coding.pl
