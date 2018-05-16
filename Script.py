### Utilities used by all bioscript programs

import sys
import os.path
import Utils

class Script():
    name = ""
    version = "1.0"
    copyright = "(c) 2017, A. Riva, DiBiG, ICBR Bioinformatics, University of Florida"
    usagefun = None
    errorNames = {}
    errorMsg = {}
    errorCode = 1

    def __init__(self, name, version="1.0", usage=None, errors=[]):
        """Errors should be a list of tuples: (code, name, message)."""
        self.name = name
        self.version = version
        self.usagefun = usage
        self.errorMsg = {}
        self.errorNames = {}
        self.defineErrors([('ERR', "Internal error", "Internal error: {}"),
                           ('NOFILE', "Missing file arguments", "Input file(s) not specified."),
                           ('BADFILE', "File not found", "Input file `{}' does not exist."),
                           ('BADINT', "Bad integer", "`{}' is not an integer number."),
                           ('BADFLOAT', "Bad float", "`{}' is not a floating point number.")])
        self.errorCode = 100
        self.defineErrors(errors)
        self.init()

    def init(self):
        pass

    def defineErrors(self, errors):
        for e in errors:
            self.errorNames[self.errorCode] = e[1]
            if len(e) == 3:
                self.errorMsg[self.errorCode] = e[2]
            else:
                self.errorMsg[self.errorCode] = e[1]
            setattr(self, e[0], self.errorCode)
            self.errorCode += 1
    
    def showErrors(self):
        for (code, name) in Utils.get_iterator(self.errorNames):
            sys.stderr.write("{}: {}\n".format(code, name))

    def usage(self, what=None):
        if what:
            self.usagefun(what)
        else:
            self.usagefun()
        sys.stderr.write(self.copyright + "\n")
        sys.exit(0)

    def getOptionValue(self, args, opts):
        """If one of the options in `opts' is present in `args', returns a tuple containing the actual argument
and the following one (if any). Otherwise, returns None."""
        nargs = len(args)
        for i in range(nargs):
            if args[i] in opts:
                if i < nargs-1:
                    return (args[i], args[i+1])
                else:
                    return (args[i],)
        return None

    def standardOpts(self, args):
        """Process the standard arguments. If any of them are found, this function does not return."""
        harg = self.getOptionValue(args, ['-h', '--help', '-E', '-v', '--version'])
        if harg:
            opt = harg[0]
            if opt == '-h' or opt == '--help':
                if len(harg) == 1:
                    self.usage()
                else:
                    self.usage(what=harg[1])
            elif opt == '-v' or opt == '--version':
                sys.stdout.write("{} version {}\n".format(self.name, self.version))
                sys.exit(0)
            elif opt == '-E':
                if len(harg) == 1:
                    self.showErrors()
                else:
                    errcode = int(harg[1])
                    if errcode in self.errorNames:
                        sys.stderr.write(self.errorNames[errcode] + "\n")
                        sys.exit(errcode)
                    else:
                        sys.stderr.write("Unknown error code {}\n".format(errcode))
                        sys.exit(0)
                sys.exit(0)

    def errmsg(self, code, *args):
        if code in self.errorMsg:
            if len(args) > 0:
                msg = self.errorMsg[code].format(*args)
            else:
                msg = self.errorMsg[code]
            sys.stderr.write("Error: " + msg + "\n")
            sys.exit(code)
        else:
            sys.stderr.write("Unknown error code {}\n".format(code))
            sys.exit(0)

    def toInt(self, x):
        try:
            return int(x)
        except ValueError:
            self.errmsg(self.BADINT, x)

    def toFloat(self, x):
        try:
            return float(x)
        except ValueError:
            self.errmsg(self.BADFLOAT, x)
        
    def isFile(self, x):
        if x == "-":
            return x
        if os.path.isfile(x):
            return x
        else:
            self.errmsg(self.BADFILE, x)
