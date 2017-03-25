#!/usr/bin/env python

import sys
import csv
import sqlite3 as sql
import Script

def usage():
    sys.stderr.write("""to be written
""")

### Program object

class Prog(Script.Script):
    source = None
    sourcetype = ""
    args = []
    distance = 2000
    gl = None                   # Gene list

    def parseArgs(self, args):
        cmd = None
        next = ""
        
        self.standardOpts(args)
        for a in args:
            if next == '-gff':
                self.source = P.isFile(a)
                self.sourcetype = 'GFF'
                next = ""
            elif next == '-db':
                self.source = P.isFile(a)
                self.sourcetype = 'DB'
                next = ""
            elif next == '-d':
                self.distance = P.toInt(a)
                next = ""
            elif a in ["-gff", "-db", "-d"]:
                next = a
            elif cmd:
                self.args.append(a)
            else:
                cmd = a
        return cmd

P = Prog("genes.py", version="1.0", usage=usage, errors=[('BADSRC', 'Missing gene database')])

# Utils

def f2dd(x):
    return "{:.2f}".format(x)

def dget(key, dict, default=None):
    if key in dict:
        return dict[key]
    else:
        return default

def parseRegion(c):
    """Parse a region specification of the form chr:start-end and return a
tuple containing the three elements. If -end is omitted, the third element
will be equal to the second one."""
    dc = c.find(":")
    if dc > 0:
        chrom = c[:dc]
        dd = c.find("-")
        if dd > 0:
            return (chrom, int(c[dc+1:dd]), int(c[dd+1:]))
        else:
            pos = int(c[dc+1:])
            return (chrom, pos, pos)
    else:
        return None

def parseCoords(c):
    """Parse a pair of coordinates in the form X..Y and return them as ints."""
    dp = c.find(".")
    if dp > 0:
        return (int(c[0:dp]), int(c[dp+2:]))
    else:
        return None

def parseStartEnd(s):
    """Parse a range specification in Genbank format. It can contain complement and join operations."""
    cl = len('complement')
    jl = len('join')
    strand = 1
    if s[0:cl] == 'complement':
        strand = -1
        s = s[cl+1:-1]
    if s[0:jl] == 'join':
        s = s[jl+1:-1]
    cp = s.find(",")
    if cp > 0:
        pairs = [ parseCoords(z) for z in s.split(",") ]
        introns = []
        for i in range(len(pairs)-1):
            introns.append((pairs[i][1], pairs[i+1][0]))
        return (pairs[0][0], pairs[-1][1], strand, introns)
    else:
        (st, en) = parseCoords(s)
        return (st, en, strand, None)

# Classes

class CSVreader():
    _reader = None
    ignorechar = '#'

    def __init__(self, stream, delimiter='\t'):
        self._reader = csv.reader(stream, delimiter=delimiter)

    def __iter__(self):
        return self

    def next(self):
        row = self._reader.next()
        if len(row) == 0 or row[0][0] == self.ignorechar:
            return self.next()
        else:
            return row

class Genelist():
    chroms = []
    genes = {}
    ngenes = 0
    indexes = {}
    btFlags = {}
    currentChrom = ""
    currentGenes = ""

    def __init__(self):
        self.chroms = []
        self.genes = {}
        self.btFlags = {"": True, "*": True}

    def saveAllToDB(self, conn):
        """Save all genes to the database represented by connection `conn'."""
        with conn:
            for chrom in self.chroms:
                for g in self.genes[chrom]:
                    g.saveToDB(conn)

    def setWanted(self, wanted):
        """Set all biotypes in `wanted' to True, all others to False."""
        for w in wanted:
            self.btFlags[w] = True
        self.btFlags["*"] = False

    def setNotWanted(self, notwanted):
        """Set all biotypes in `notwanted' to False, all others to True."""
        for w in notwanted:
            self.btFlags[w] = False
        self.btFlags["*"] = True

    def add(self, gene, chrom):
        bt = gene.biotype
        if bt in self.btFlags:
            w = self.btFlags[bt]
        else:
            w = self.btFlags["*"]
        if w:
            if chrom not in self.chroms:
                self.chroms.append(chrom)
                self.genes[chrom] = []
            self.genes[chrom].append(gene)
            self.ngenes += 1

    def selectChrom(self, chrom):
        if chrom <> self.currentChrom and chrom in self.chroms:
            self.currentChrom = chrom
            self.currentGenes = self.genes[chrom]
        return self.currentGenes

    def genesOnChrom(self, chrom):
        if chrom in self.genes:
            return self.selectChrom(chrom)
        else:
            return []

    def allGeneNames(self):
        result = []
        for (chrom, cgenes) in self.genes.iteritems():
            for cg in cgenes:
                result.append(cg.name)
        return result

    def findGene(self, name, chrom=None):
        if chrom:
            cgenes = self.genes[chrom]
            for g in cgenes:
                if g.ID == name or g.name == name:
                    return g
            return None
        else:
            for ch in self.chroms:
                g = self.findGene(name, chrom=ch)
                if g:
                    return g
            return None

    def sortGenes(self):
        for chrom in self.chroms:
            self.genes[chrom].sort(key=lambda g:g.start)

    def buildIndexes(self):
        step = 100
        idxs = {}
        for chrom, genes in self.genes.iteritems():
            ng = len(genes)
            d = []
            # print "chr={}, genes={}".format(chrom, len(genes))
            for i in range(0, len(genes), step):
                i2 = min(i+step, ng) - 1
                # print "i1={}, i2={}".format(i, i+step-1)
                gfirst = genes[i]
                glast  = genes[i2]
                d.append([gfirst.start, glast.end, i, i2])
            idxs[chrom] = d
            # print d
            # raw_input()
        self.indexes = idxs

    def positionsToRange(self, chrom, start, end):
        """Returns the first and last index for genes in the range `start' to `end'."""
        first = last = 0
        if chrom in self.indexes:
            idxs = self.indexes[chrom]
            for i in range(0, len(idxs)):
                iblock = idxs[i]
                if iblock[0] <= start <= iblock[1]:
                    sb = iblock
                    eb = iblock
                    if i > 0:
                        sb = idxs[i-1]
                    if i < len(idxs) - 1:
                        eb = idxs[i+1]
                    first = sb[2]
                    last  = eb[3]
                    break
        return (first, last)

    def classifyIntersection(self, astart, aend, g):
        """A is mine, B is other."""
        bstart = g.txstart
        bend   = g.txend
        if astart < bstart:
            if bstart <= aend <= bend:
                how = 'left'
                alen = aend-astart+1
                blen = bend-bstart+1
                isiz = aend-bstart+1
                return (g, how, 1.0*isiz/alen, 1.0*isiz/blen)
            elif aend > bend:
                how = 'contains'
                alen = aend-astart+1
                isiz = bend-bstart+1
                return (g, how, 1.0*isiz/alen, 1.0)
        elif bstart <= astart <= bend:
            if aend <= bend:
                how = 'contained'
                blen = bend-bstart+1
                isiz = aend-astart+1
                return (g, how, 1.0, 1.0*isiz/blen)
            else:
                how = 'right'
                alen = aend-astart+1
                blen = bend-bstart+1
                isiz = bend-astart+1
                return (g, how, 1.0*isiz/alen, 1.0*isiz/blen)
        return None

    def allIntersecting(self, chrom, start, end):
        """Returns all genes in `chrom' that intersect the `start-end' region."""
        result = []
        self.selectChrom(chrom)
        genes = self.currentGenes
        (first, last) = self.positionsToRange(chrom, start, end)
        # print "Looking at {}-{}".format(first, last)
        for i in range(first, last+1):
            ix = self.classifyIntersection(start, end, genes[i])
            if ix:
                result.append(ix)
        return result
        
    def intersectFromBED(self, bedfile, outfile):
        with open(outfile, "w") as out:
            with open(bedfile, "r") as f:
                f.readline()
                for line in f:
                    parsed = line.rstrip("\n\r").split("\t")
                    allint = self.allIntersecting(parsed[0], int(parsed[1]), int(parsed[2]))
                    for a in allint:
                        g = a[0]
                        out.write("\t".join(parsed + [g.name, g.biotype, a[1], f2dd(a[2]*100), f2dd(a[3]*100)]) + "\n")

    def notIntersectFromBED(self, bedfile, outfile):
        with open(outfile, "w") as out:
            with open(bedfile, "r") as f:
                f.readline()
                for line in f:
                    parsed = line.rstrip("\n\r").split("\t")
                    s = int(parsed[1])
                    e = int(parsed[2])
                    allint = self.allIntersecting(parsed[0], s, e)
                    if allint == []:
                        out.write("\t".join(parsed) + "\t{}\n".format(1+e-s))

    def intronsToBED(self, bedfile):
        with open(bedfile, "w") as out:
            for chrom in self.chroms:
                for gene in self.genes[chrom]:
                    intid = 1
                    prevexon = gene.exons[0]
                    for ex in gene.exons[1:]:
                        start = prevexon[1] + 1
                        end = ex[0] - 1
                        if gene.strand == 1:
                            out.write("{}\t{}\t{}\t{}_{}\t{}\t{}\n".format(chrom, start, end, gene.mrna, intid, gene.name, gene.strand))
                        else:
                            out.write("{}\t{}\t{}\t{}_{}\t{}\t{}\n".format(chrom, end, start, gene.mrna, intid, gene.name, gene.strand))
                            # print [chrom, end, start, gene.mrna, intid, gene.name, gene.strand]
                            # raw_input()
                        intid += 1
                        prevexon = ex

    def junctionsToBED(self, bedfile, size=5):
        with open(bedfile, "w") as out:
            for chrom in self.chroms:
                for gene in self.genes[chrom]:
                    intid = 1
                    for ex in gene.exons:
                        out.write("{}\t{}\t{}\t{}_{}_a\t{}\t{}\n".format(chrom, ex[0]-10, ex[0]+10, gene.mrna, intid-1, gene.name, gene.strand))
                        out.write("{}\t{}\t{}\t{}_{}_b\t{}\t{}\n".format(chrom, ex[1]-10, ex[1]+10, gene.mrna, intid, gene.name, gene.strand))
                        intid += 1

class GenelistDB(Genelist):
    conn = None                 # DB connection
    preloaded = False           # Did we preload all genes into the Genelist?

    def findGene(self, name, chrom=None):
        gcur = self.conn.cursor()
        tcur = self.conn.cursor()
        ecur = self.conn.cursor()
        gcur.execute("SELECT ID, name, geneid, ensg, biotype, chrom, strand, start, end FROM Genes WHERE ID=? OR name=? OR geneid=? OR ensg=?", 
                     (name, name, name, name))
        row = gcur.fetchone()
        if row:
            gid = row[0]
            g = Gene(gid, row[5], row[6])
            for pair in zip(['ID', 'name', 'geneid', 'ensg', 'biotype', 'chrom', 'strand', 'start', 'end'], row):
                setattr(g, pair[0], pair[1])
            for trow in tcur.execute("SELECT ID, name, accession, enst, chrom, strand, txstart, txend, cdsstart, cdsend FROM Transcripts WHERE parentID=?", (gid,)):
                tid = trow[0]
                tr = Transcript(tid, trow[4], trow[5], trow[6], trow[7])
                tr.exons = []
                for pair in zip(['ID', 'name', 'accession', 'enst', 'chrom', 'strand', 'txstart', 'txend', 'cdsstart', 'cdsend'], trow):
                    setattr(tr, pair[0], pair[1])
                for erow in ecur.execute("SELECT start, end FROM Exons WHERE ID=? ORDER BY idx", (tid,)):
                    tr.addExon(erow[0], erow[1])
                g.addTranscript(tr)
            return g
        else:
            return None

    def findGenes(self, query, args):
        result = []
        qcur = self.conn.cursor()
        gcur = self.conn.cursor()
        tcur = self.conn.cursor()
        ecur = self.conn.cursor()
        for geneIDrow in qcur.execute(query, args):
            geneID = geneIDrow[0]
            row = gcur.execute("SELECT ID, name, geneid, ensg, biotype, chrom, strand, start, end FROM Genes WHERE ID=?", (geneID,)).fetchone()
            if row:
                gid = row[0]
                g = Gene(gid, row[5], row[6])
                for pair in zip(['ID', 'name', 'geneid', 'ensg', 'biotype', 'chrom', 'strand', 'start', 'end'], row):
                    setattr(g, pair[0], pair[1])
                for trow in tcur.execute("SELECT ID, name, accession, enst, chrom, strand, txstart, txend, cdsstart, cdsend FROM Transcripts WHERE parentID=?", (gid,)):
                    tid = trow[0]
                    tr = Transcript(tid, trow[4], trow[5], trow[6], trow[7])
                    tr.exons = []
                    for pair in zip(['ID', 'name', 'accession', 'enst', 'chrom', 'strand', 'txstart', 'txend', 'cdsstart', 'cdsend'], trow):
                        setattr(tr, pair[0], pair[1])
                    for erow in ecur.execute("SELECT start, end FROM Exons WHERE ID=? ORDER BY idx", (tid,)):
                        tr.addExon(erow[0], erow[1])
                    g.addTranscript(tr)
                result.append(g)
        return result

    def allIntersecting(self, chrom, start, end):
        """Returns all genes in `chrom' that intersect the `start-end' region."""
        return self.findGenes("SELECT ID from Genes where chrom=? and ((? <= start) and (start <= ?) or ((? <= end) and (end <= ?)) or ((start <= ?) and (end >= ?)))",
                              (chrom, start, end, start, end, start, end))

# Gene class

class Transcript():
    ID = ""
    name = ""
    chrom = ""
    strand = ""
    accession = ""
    enst = ""
    txstart = 0
    txend = 0
    cdsstart = None
    cdsend = None
    strand = None
    exons = []
    smallrects = []
    largerects = []

    def __init__(self, ID, chrom, strand, txstart, txend):
        self.ID = ID
        self.chrom = chrom
        self.strand = strand
        self.txstart = txstart
        self.txend = txend
        self.exons = [(txstart, txend)] # We initially assume transcript has no introns
        self.smallrects = []
        self.largerects = []

    def dump(self, prefix="", short=False):
        if short:
            print "{}{} {}:{}-{} {}".format(prefix, self.ID, self.chrom, self.txstart, self.txend, self.exons)
        else:
            print prefix + "ID: " + self.ID
            print prefix + "Chrom: " + self.chrom
            print "{}Strand: {}".format(prefix, self.strand)
            print "{}Transcript: {}-{}".format(prefix, self.txstart, self.txend)
            print "{}CDS: {}-{}".format(prefix, self.cdsstart, self.cdsend)
            print "{}Exons: {}".format(prefix, self.exons)

    def saveToDB(self, conn, parentID):
        with conn:
            idx = 0
            for ex in self.exons:
                conn.execute("INSERT INTO Exons(ID, idx, chrom, start, end) VALUES (?, ?, ?, ?, ?);",
                             (self.ID, idx, self.chrom, ex[0], ex[1]))
                idx += 1

            conn.execute("INSERT INTO Transcripts (ID, parentID, name, accession, enst, chrom, strand, txstart, txend, cdsstart, cdsend) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
                         (self.ID, parentID, self.name, self.accession, self.enst, self.chrom, self.strand, self.txstart, self.txend, self.cdsstart, self.cdsend))

    def addExon(self, start, end):
        self.exons.append((start, end))

    def setIntrons(self, introns):
        self.exons = [(self.txstart, introns[0][0])]
        for i in range(len(introns)-1):
            self.exons.append((introns[i][1], introns[i+1][0]))
        self.exons.append((introns[-1][1], self.txend))

    def setCDS(self, cdsstart, cdsend):
        """Set the CDS of this transcript to `cdsstart' and `cdsend'. This also sets the
smallrects and largerects lists."""
        self.cdsstart = cdsstart
        self.cdsend   = cdsend
        self.smallrects = []    # we're recomputing them
        self.largerects = []    # from scratch
        small = True
        for e in self.exons:
            if (e[0] <= self.cdsstart < self.cdsend <= e[1]): # CDS entirely contained in exon?
                self.smallrects.append((e[0], self.cdsstart))
                self.largerects.append((self.cdsstart, self.cdsend))
                self.smallrects.append((self.cdsend, e[1]))
            elif (e[0] <= self.cdsstart <= e[1]):             # Exon contains start of CDS? 
                self.smallrects.append((e[0], self.cdsstart))
                self.largerects.append((self.cdsstart, e[1]))
                small = False
            elif (e[0] <= self.cdsend <= e[1]):               # Exon contains end of CDS?
                self.largerects.append((e[0], self.cdsend))
                self.smallrects.append((self.cdsend, e[1]))
                small = True
            elif small:
                self.smallrects.append(e)
            else:
                self.largerects.append(e)

    def posInExon(self, pos):
        """Return True if position `pos' is in one of the exons of this transcript."""
        for e in self.exons:
            if e[0] <= pos <= e[1]:
                return True
        return False

    def positionMatch(self, pos, mode, distance):
        """Return True if position `pos' matches transcript according to `mode'.
`mode' can be one of b, P, d, e, or i. `distance' is used when `mode' includes p or d."""
        for m in mode:
            if m == 'b':
                if self.txstart <= pos <= self.txend:
                    return True
            elif m == 'p':
                if self.strand == 1:
                    if self.txstart - distance <= pos < self.txstart:
                        return True
                else:
                    if self.txend < pos <= self.txend + distance:
                        return True
            elif m == 'd':
                if self.strand == -1:
                    if self.txstart - distance <= pos < self.txstart:
                        return True
                else:
                    if self.txend < pos <= self.txend + distance:
                        return True
            else:
                ex = self.posInExon(pos)
                if m == 'e' and ex:
                    return True
                if m == 'i' and not ex:
                    return True
        return False

    def classifyPosition(self, pos, distance):
        """Returns a single character that classifies position `pos' within this transcript.
Possible return values are 'p' (up to `distance' bp upstream of the transcript), 'd'
(up to `distance' bp downstream of the transcript), 'E' (in a coding exon), 'e' (in a
non-coding exon), 'i' (in an intron)."""
        if pos < self.txstart - distance or pos > self.txend + distance:
            return False

        if pos < self.txstart:
            if self.strand == 1:
                return 'p'
            else:
                return 'd'
        if pos > self.txend:
            if self.strand == 1:
                return 'd'
            else:
                return 'p'
        if self.posInExon(pos):
            if self.cdsstart <= pos <= self.cdsend:
                return 'E'
            else:
                return 'e'
        return 'i'

    def geneLimits(self, upstream, downstream, ref='B'):
        """Returns the start and end coordinates of a region extending from `upstream' bases
upstream of the TSS to `downstream' bases downstream of the TSE. If `ref' is equal to S, both
coordinates are computed according to the TSS, and if it is 'E', both coordinates are computed
according to the TSE. Takes strand of transcript into account."""
        if ref == 'B':
            if self.strand == 1:
                return (self.txstart - upstream, self.txend + downstream)
            else:
                return (self.txstart - downstream, self.txend + upstream)
        elif ref == 'S':
            if self.strand == 1:
                return (self.txstart - upstream, self.txstart + downstream)
            else:
                return (self.txend - downstream, self.txend + upstream)
        elif ref == 'E':
            if self.strand == 1:
                return (self.txend - upstream, self.txend + downstream)
            else:
                return (self.txend - downstream, self.txend + upstream)

    def distanceFrom(self, position, ref='S'):
        """Returns the distance from `position' to the TSS (if ref=S) or the TSE (if ref=E).
The distance is negative if `position' is upstream of the reference point, positive if
downstream."""
        if ref == 'S':
            if self.strand == 1:
                return position - self.txstart
            else:
                return self.txend - position
        else:
            if self.strand == 1:
                return position - self.txend
            else:
                return self.txend - position

class Gene():
    ID = ""
    name = ""
    geneid = ""
    ensg = ""
    biotype = ""
    chrom = ""
    strand = ""
    start = None                # leftmost txstart
    end = None                  # rightmost txend
    transcripts = []
    data = []

    def __init__(self, ID, chrom, strand):
        self.ID          = ID
        self.chrom       = chrom
        self.strand      = strand
        self.transcripts = []
        self.data        = []

    def dump(self):
        print "ID: " + self.ID
        print "Gene: " + self.name
        print "GeneID: " + self.geneid
        print "Chrom: " + self.chrom
        print "Strand: {}".format(self.strand)
        print "Transcripts:"
        for t in self.transcripts:
            t.dump(prefix="  ", short=True)

    def saveToDB(self, conn):
        with conn:
            for tr in self.transcripts:
                tr.saveToDB(conn, self.ID)
            conn.execute("INSERT INTO Genes (ID, name, geneid, ensg, biotype, chrom, strand, start, end) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);",
                         (self.ID, self.name, self.geneid, self.ensg, self.biotype, self.chrom, self.strand, self.start, self.end))

    def addTranscript(self, transcript):
        self.transcripts.append(transcript)
        if self.start:
            self.start = min(self.start, transcript.txstart)
        else:
            self.start = transcript.txstart
        if self.end:
            self.end = max(self.end, transcript.txend)
        else:
            self.end = transcript.txend

    def classifyPosition(self, position, distance):
        """Returns a string containing all possible classifications of `position' for the transcript of this gene."""
        result = []
        for tr in self.transcripts:
            c = tr.classifyPosition(position, distance)
            if c and c not in result:
                result.append(c)
        return "".join(sorted(result))

class GeneLoader():
    gl = None
    filename = ""
    currGene = None
    currTranscript = None

    def __init__(self, filename):
        self.filename = filename
        self.gl = Genelist()

    def validateChrom(self, chrom):
        if chrom.find("_") > 0:
            return False
        if chrom.find("random") > 0:
            return False
        if not chrom.startswith('chr') or chrom.startswith('Chr'):
            chrom = "chr" + chrom
        return chrom

    def load(self, sort=True, index=True):
        self._load()
        if sort:
            self.gl.sortGenes()
        if index:
            self.gl.buildIndexes()
        return self.gl

class refGeneLoader(GeneLoader):
    genes = {}                  # Dictionary of genes by name

    def _load(self):
        self.genes = {}
        with open(self.filename, "r") as f:
            reader = CSVreader(f)
            for line in reader:
                chrom = self.validateChrom(line[2])
                if chrom:
                    name = line[12]
                    if name in self.genes:
                        self.currGene = self.genes[name]
                    else:
                        self.currGene = self.genes[name] = Gene(name, chrom, line[3])
                        self.currGene.name = name
                        self.gl.add(self.currGene, chrom)
                    transcript = Transcript(line[1], chrom, line[3], int(line[4]), int(line[5]))
                    transcript.accession = line[1]
                    transcript.exons = zip(line[9].rstrip(",").split(","), line[10].rstrip(",").split(","))
                    transcript.setCDS(int(line[6]), int(line[7]))
                    self.currGene.addTranscript(transcript)

class GenbankLoader(GeneLoader):

    def _load(self):
        chrom = ""
        thisGene = None
        start = None
        end = None
        strand = None
        cdsstart = None
        cdsend = None
        section = ""

        infeatures = False
        with open(self.filename, "r") as f:
            for line in f:
                line = line.rstrip("\r\n")
                if infeatures:
                    key = line[0:20].strip()
                    if key == '':   # still in previous section?
                        if section == 'gene':
                            data = line[21:]
                            # print "In gene section: {}".format(data)
                            if data[0:5] == '/gene':
                                # print "Setting name to {}".format(data[7:-1])
                                thisGene.name = thisGene.ID = data[7:-1]
                            elif data[0:10] == '/locus_tag':
                                if thisGene.name == '':
                                    thisGene.name = data[12:-1]
                                if thisGene.ID == '':
                                    thisGene.ID = data[12:-1]
                    elif key == 'gene':
                        # print "Found new gene"
                        # raw_input()
                        section = key
                        start, end, strand, ignore = parseStartEnd(line[21:])
                        # print "New gene at ({}, {})".format(start, end)
                        thisGene = Gene("", chrom, strand)
                        thisGene.chrom = chrom
                        self.gl.add(thisGene, chrom)
                        thisGene.addTranscript(Transcript("", chrom, strand, start, end))
                    elif key == 'CDS':
                        cdsstart, cdsend, ignore, introns = parseStartEnd(line[21:])
                        # print "Setting CDS to ({}, {})".format(cdsstart, cdsend)
                        if introns:
                            # print "Setting introns: {}".format(introns)
                            thisGene.transcripts[0].setIntrons(introns)

                        thisGene.transcripts[0].setCDS(cdsstart, cdsend)
                        # print thisGene.smallrects
                        # print thisGene.largerects
                    else:
                        section = ''
                elif line[0:9] == 'ACCESSION': # 'LOCUS':
                    chrom = line[12:line.find(" ", 12)]
                elif line[0:8] == 'FEATURES':
                    infeatures = True

class GTFloader(GeneLoader):

    def parseAnnotations(self, ann):
        """Parse GTF annotations `ann' and return them as a dictionary."""
        anndict = {}
        pieces = [ s.strip(" ") for s in ann.split(";") ]
        for p in pieces:
            f = p.find(" ")
            if f > 0:
                key = p[0:f]
                val = p[f+1:].strip('"')
                anndict[key] = val
        return anndict

    def _load(self, wanted=[], notwanted=[]):
        """Read genes from a DTF file `filename'. If `wanted' is specified, only include genes whose biotype
is in this list (or missing). If `notwanted' is specified, only include genes whose biotype is not in this list (or missing)."""
        g = None                # Current gene
        gt = None               # Current transcript

        if wanted <> []:
            self.gl.setWanted(wanted)
        elif notwanted <> []:
            self.gl.setNotWanted(notwanted)

        with open(filename, "r") as f:
            reader = CSVreader(f)
            for line in f:
                if line[6] == '+':
                    strand = 1
                else:
                    strand = -1
                chrom = self.validateChrom(line[0])
                if not chrom:
                    continue    # skip this entry
                btype = line[2]
                if btype == 'gene':
                    if False: # gt:
                        gt.setCDS(g.cdsstart, g.cdsend)
                        g.dump()
                        raw_input()
                        genes.add(gt, gt.chrom)
                    g = Gene([], chrom=chrom, strand=strand) 
                    gt = None
                    ann = parseAnnotations(line[8])
                    if 'gene_name' in ann:
                        g.name = ann['gene_name']
                    else:
                        g.name = ann['gene_id']
                    g.geneid = ann['gene_id']
                    g.biotype = ann['gene_biotype']
                elif btype == 'transcript':
                    if gt:
                        gt.setCDS(gt.cdsstart, gt.cdsend)
                        # gt.dump()
                        # raw_input()
                    gt = Gene([], chrom=g.chrom, strand=g.strand) # clone gene into transcript
                    gt.name = g.name
                    gt.geneid = g.geneid
                    gt.biotype = g.biotype
                    gt.txstart = int(line[3])
                    gt.txend   = int(line[4])
                    ann = parseAnnotations(line[8])
                    gt.mrna = ann['transcript_id']
                    gt.txname = dget('transcript_name', ann)
                    genes.add(gt, gt.chrom)
                elif btype == 'CDS':
                    start = int(line[3])
                    end   = int(line[4])
                    if gt.cdsstart == None:
                        gt.cdsstart = start
                    gt.cdsend = end
                elif btype == 'exon':
                    start = int(line[3])
                    end   = int(line[4])
                    # print (start, end)
                    gt.exons.append((start, end))
        genes.add(gt, gt.chrom)

class GFFloader(GeneLoader):

    def parseAnnotations(self, ann):
        anndict = {}
        pieces = [ s.strip(" ") for s in ann.split(";") ]
        for p in pieces:
            pair = p.split("=")
            if len(pair) == 2:
                anndict[pair[0]] = pair[1].strip('"')
        return anndict

    def cleanID(self, idstring):
        if not idstring:
            return ""
        if idstring.startswith("gene:"):
            return idstring[5:]
        if idstring.startswith("transcript:"):
            return idstring[11:]
        return idstring

    def _load(self, wanted=[], notwanted=[]):
        chrom = ""
        strand = 0
        orphans = 0             # Entries not following their parents

        if wanted <> []:
            self.gl.setWanted(wanted)
        elif notwanted <> []:
            self.gl.setNotWanted(notwanted)

        with open(self.filename, "r") as f:
            reader = CSVreader(f)
            for line in reader:
                if len(line) < 8:
                    print "|"+line+"|"
                if line[6] == '+':
                    strand = 1
                else:
                    strand = -1
                chrom = self.validateChrom(line[0])
                if not chrom:
                    continue
                tag = line[2]

                if tag in ['gene', 'miRNA_gene', 'lincRNA_gene']:
                    ann   = self.parseAnnotations(line[8])
                    gid   = self.cleanID(dget('ID', ann))
                    self.currGene = Gene(gid, chrom, strand)
                    self.currGene.name = dget('Name', ann, "")
                    self.currGene.biotype = dget('biotype', ann)
                    self.gl.add(self.currGene, chrom)
                    
                elif tag in ['mRNA', 'transcript', 'processed_transcript', 'pseudogenic_transcript', 'pseudogene', 'processed_pseudogene', 'miRNA', 'lincRNA']:
                    ann = self.parseAnnotations(line[8])
                    tid = self.cleanID(dget('ID', ann))
                    pid = self.cleanID(dget('Parent', ann))
                    self.currTranscript = Transcript(tid, chrom, strand, int(line[3]), int(line[4]))
                    self.currTranscript.name = dget('Name', ann, "")
                    self.currTranscript.biotype = dget('biotype', ann)
                    self.currTranscript.exons = [] # Exons come later in the file
                    if pid == self.currGene.ID:
                        self.currGene.addTranscript(self.currTranscript)
                    else:
                        orphans += 1

                elif tag == 'exon':
                    ann = self.parseAnnotations(line[8])
                    pid = self.cleanID(dget('Parent', ann))
                    if pid == self.currTranscript.ID:
                        start = int(line[3])
                        end   = int(line[4])
                        self.currTranscript.addExon(start, end)
                    else:
                        orphans += 1

                elif tag == 'CDS':
                    ann = self.parseAnnotations(line[8])
                    pid = self.cleanID(dget('Parent', ann))
                    if pid == self.currTranscript.ID:
                        start = int(line[3])
                        end   = int(line[4])
                        self.currTranscript.setCDS(start, end)
                    else:
                        orphans += 1

        sys.stderr.write("Orphans: {}\n".format(orphans))

class DBloader(GeneLoader):
    conn = None

    def _load(self, preload=False, wanted=[], notwanted=[]):
        self.gl = GenelistDB()
        self.gl.preloaded = preload
        self.conn = sql.connect(self.filename)
        self.gl.conn = self.conn
        if preload:
            gcur = self.conn.cursor()
            tcur = self.conn.cursor()
            ecur = self.conn.cursor()
            for row in gcur.execute("SELECT ID, name, geneid, ensg, biotype, chrom, strand, start, end FROM Genes"):
                gid = row[0]
                g = Gene(gid, row[5], row[6])
                for pair in zip(['ID', 'name', 'geneid', 'ensg', 'biotype', 'chrom', 'strand', 'start', 'end'], row):
                    setattr(g, pair[0], pair[1])
                self.gl.add(g, g.chrom)
                for trow in tcur.execute("SELECT ID, name, accession, enst, chrom, strand, txstart, txend, cdsstart, cdsend FROM Transcripts WHERE parentID=?", (gid,)):
                    tid = trow[0]
                    tr = Transcript(tid, trow[4], trow[5], trow[6], trow[7])
                    for pair in zip(['ID', 'name', 'accession', 'enst', 'chrom', 'strand', 'txstart', 'txend', 'cdsstart', 'cdsend'], trow):
                        setattr(tr, pair[0], pair[1])
                    for erow in ecur.execute("SELECT start, end FROM Exons WHERE ID=? ORDER BY idx", (tid,)):
                        tr.addExon(erow[0], erow[1])
                    g.addTranscript(tr)
        else:
            row = self.conn.execute("SELECT count(*) FROM Genes").fetchone()
            self.gl.ngenes = row[0]

### Database stuff

def initializeDB(filename):
    """Create a new database in 'filename' and write the Genes, Transcripts, and Exons tables to it."""
    conn = sql.connect(filename)
    conn.execute("DROP TABLE IF EXISTS Genes;")
    conn.execute("CREATE TABLE Genes (ID varchar primary key, name varchar, geneid varchar, ensg varchar, biotype varchar, chrom varchar, strand int, start int, end int);")
    for field in ['name', 'geneid', 'ensg', 'chrom', 'start', 'end']:
        conn.execute("CREATE INDEX Genes_{} on Genes({});".format(field, field))
    conn.execute("DROP TABLE IF EXISTS Transcripts;")
    conn.execute("CREATE TABLE Transcripts (ID varchar primary key, parentID varchar, name varchar, accession varchar, enst varchar, chrom varchar, strand int, txstart int, txend int, cdsstart int, cdsend int);")
    for field in ['parentID', 'name', 'accession', 'enst', 'chrom', 'txstart', 'txend']:
        conn.execute("CREATE INDEX Trans_{} on Transcripts({});".format(field, field))
    conn.execute("DROP TABLE IF EXISTS Exons;")
    conn.execute("CREATE TABLE Exons (ID varchar, idx int, chrom varchar, start int, end int);")
    for field in ['ID', 'chrom', 'start', 'end']:
        conn.execute("CREATE INDEX Exon_{} on Exons({});".format(field, field))
    conn.close()
    
### Main

def loadGenes(source, format):
    if format == 'GFF':
        l = GFFloader(source)
    elif format == 'DB':
        l = DBloader(source)
    else:
        P.errmsg(P.BADSRC)
    sys.stderr.write("Loading genes from {} database {}... ".format(format, source))
    gl = l.load()
    sys.stderr.write("{} genes loaded.\n".format(gl.ngenes))
    return gl

def main(args):
    cmd = P.parseArgs(args)
    P.gl = loadGenes(P.source, P.sourcetype)
    if cmd == 'region':         # Print the region for the genes passed as arguments.
        if len(P.args) == 0:
            P.errmsg()
        for name in P.args:
            gene = P.gl.findGene(name)
            if gene:
                sys.stdout.write("{}\t{}:{}-{}\n".format(name, gene.chrom, gene.start, gene.end))
            else:
                sys.stderr.write("No gene `{}'.\n".format(name))
    elif cmd == 'transcripts':  # Display the transcripts for the genes passed as arguments.
        if len(P.args) == 0:
            P.errmsg()
        sys.stdout.write("Gene\tID\tName\tAccession\tChrom\tTXstart\tTXend\tExons\n")
        for name in P.args:
            gene = P.gl.findGene(name)
            if gene:
                for tx in gene.transcripts:
                    sys.stdout.write("{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\n".format(name, tx.ID, tx.name, tx.accession, tx.chrom, tx.txstart, tx.txend, ",".join(["{}-{}".format(e[0], e[1]) for e in tx.exons])))
            else:
                sys.stderr.write("No gene `{}'.\n".format(name))
    elif cmd == 'classify':  # Classify the given position (chr:pos) according to the transcripts it falls in
        reg = parseRegion(P.args[0])
        pos = reg[1]
        genes = P.gl.allIntersecting(reg[0], pos - P.distance, pos + P.distance)
        # sys.stdout.write("Gene\tID\tAccession\tClass\n")
        sys.stdout.write("Gene\tID\tClass\n")
        for g in genes:
            name = g.name
            c = g.classifyPosition(pos, P.distance)
            sys.stdout.write("{}\t{}\t{}\n".format(g.name, g.ID, c))
            # for tr in g.transcripts:
            #     c = tr.classifyPosition(pos, P.distance)
            #     sys.stdout.write("{}\t{}\t{}\t{}\n".format(g.name, tr.ID, tr.accession, c))

if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) > 0:
        main(args)
    else:
        P.errmsg(P.NOCMD)