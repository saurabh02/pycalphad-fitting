"""
This module handles conversion of POP files to JSON files in ESPEI format
"""

from pyparsing import *

from pop_keywords import expand_keyword, POP_COMMANDS

print("""WARNING! This module is VERY experimental. You will most likely get failures or incorrect answers.
You should check all of your data instead of assuming it is correct.
Please report any errors so that this module can be improved.""")

class ExperimentSet(dict):
    """
    Experiment set, which is a stored as a dictionary.

    The reason for the subclass is to store metadata about the experiment set while it is being
    constructed by parsing. Once it is constructed, there is no use for having a class because the
    data will be fully populated as a normal dictionary.
    """

    def __init__(self):
        self._columns = None
        super(ExperimentSet, self).__init__()

    @property
    def columns(self):
        return self._columns

    def update(self, E=None, **F):
        """
        Overrides dict update to return self (for lambda functions)
        """
        super(ExperimentSet, self).update(E, **F)
        return self


class POPCommand(CaselessKeyword):
    """
    Parser element for dealing with POP command abbreviations.
    """
    def parseImpl(self, instring, loc, doActions=True):
        # Find the end of the keyword by searching for an end character
        # TODO: how much of this do I need?
        start = loc
        endchars = ' ():,'
        loc = -1
        for charx in endchars:
            locx = instring.find(charx, start)
            if locx != -1:
                # match the end-character closest to the start character
                if loc != -1:
                    loc = min(loc, locx)
                else:
                    loc = locx
        # if no end character found, just match the whole thing
        if loc == -1:
            loc = len(instring)
        try:
            res = expand_keyword([self.match], instring[start:loc])
            if len(res) > 1:
                self.errmsg = '{0!r} is ambiguous: matches {1}' \
                    .format(instring[start:loc], res)
                raise ParseException(instring, loc, self.errmsg, self)
            # res[0] is the unambiguous expanded keyword
            # in principle, res[0] == self.match
            return loc, res[0]
        except ValueError:
            pass
        raise ParseException(instring, loc, self.errmsg, self)


def _pop_grammar():
    """
    Returns the pyparsing grammar for a POP file.
    """
    # pyparsing "constants"
    sCOMMA = Suppress(',') # supresses
    int_number = Word(nums).setParseAction(lambda t: [int(t[0])])
    # matching float w/ regex is ugly but is recommended by pyparsing
    float_number = (Regex(r'[-+]?[0-9]*\.?[0-9]+([eE][-+]?[0-9]+)?') | '0')  \
        .setParseAction(lambda t: [float(t[0])])
    # symbol name, e.g., phase name or equilibrium name
    symbol_name = Word(alphanums+'_:', min=1)
    equalities = Word('=') ^ Word('<') ^ Word('>')
    pm = oneOf('+ -')
    label = Word('@'+nums)
    value = (float_number | int_number | label | symbol_name)
    const = Group(symbol_name + equalities + value)
    phases = Group(OneOrMore(symbol_name + Optional(sCOMMA))) | '*'
    prop_prefix = symbol_name + Suppress('(') + phases + Suppress(')')
    property = Group(prop_prefix + equalities + value)
    expr = Group(OneOrMore(prop_prefix | float_number | oneOf('. + - / * ( )') | symbol_name))
    arith_cond = Group(OneOrMore(Optional(Word(nums) + '*')+ prop_prefix + Optional(pm)) + equalities + value) # an arithmetic matcher for complex conditions
    error = Group(Suppress(':') + float_number + Optional('%'))
    cmd_equilibrium = POPCommand('CREATE_NEW_EQUILIBRIUM') + (Word('@@,') ^ int_number) + Optional(sCOMMA) + int_number
    # TODO: implement changing status of other things
    phase_statuses = ((POPCommand('FIXED') ^ POPCommand('ENTERED')) + float_number) | POPCommand('DORMANT') | POPCommand('SUSPENDED')
    cmd_change_status = POPCommand('CHANGE_STATUS') + POPCommand('PHASE') + phases + Suppress('=') + phase_statuses
    enter_const = POPCommand('CONSTANTS') +  OneOrMore(const)
    enter_func_var = (POPCommand('FUNCTION') | POPCommand('VARIABLE')) + symbol_name + '=' + expr
    enter_table = POPCommand('TABLE') # TODO: implement
    cmd_en_symbol = POPCommand('ENTER_SYMBOL') + (enter_const | enter_func_var | enter_table)
    cmd_table_head = POPCommand('TABLE_HEAD') + int_number
    cmd_table_values = POPCommand('TABLE_VALUES') + sCOMMA + Group(delimitedList(Group(OneOrMore(float_number)))) + Suppress(POPCommand('TABLE_END'))
    cmd_set_ref_state = POPCommand('SET_REFERENCE_STATE') + symbol_name + symbol_name + Optional(OneOrMore(sCOMMA)) # TODO: should these default values be handled?
    cmd_set_condition = POPCommand('SET_CONDITION') + OneOrMore(( arith_cond | property | const ) + Optional(error) + Optional(sCOMMA))
    cmd_label = POPCommand('LABEL_DATA') + OneOrMore(Word(alphanums))
    cmd_experiment_phase = POPCommand('EXPERIMENT') + OneOrMore(Group((property | const) + error) + Optional(sCOMMA))
    cmd_experiment_const = POPCommand('EXPERIMENT') + const + error
    cmd_start_value = POPCommand('SET_START_VALUE') + property
    cmd_save = POPCommand('SAVE_WORKSPACE')
    return (cmd_equilibrium | cmd_change_status |cmd_en_symbol | cmd_table_head | cmd_table_values |
           cmd_set_ref_state | cmd_set_condition | cmd_label | cmd_experiment_const |
           cmd_experiment_phase | cmd_start_value | cmd_save) + Optional(Suppress(';')) #+ stringEnd

def unpack_parse_results(parse_results):
    """
    Recursively unpacks parse results and return the unpacked result.

    Args:
        parse_results (ParseResults): a tuple of a list of values and dict of names. The list may contain nested ParseResults
    """
    results_list = []
    for result in parse_results:
        if isinstance(result, ParseResults):
            results_list.append(unpack_parse_results(result))
        else:
            results_list.append(result)
    return results_list

def _unimplemented(*args, **kwargs):
    """
    Wrapper to raise NotImplementedError

    This should be used when a command that affects the data is unimplmented. If the command does not
    affect the data, then `_pass` should be used.
    """
    raise NotImplementedError

def _pass(*args, **kwargs):
    """
    Pass is intended for POP commands that do not impact the data

    Commands that do impact the data should use `_unimplemented`
    """
    return args[0] # return the experiment unchanged

def _new_equilibrium(_, _1, code):
    # initialization codes
    # 0: suspend all phases and components
    # 1: enter all components only
    # 2: enter all
    if code == 1:
        return ExperimentSet()
    else:
        raise NotImplementedError

_POP_PROCESSOR = {
    'TABLE_HEAD': _pass,
    'TABLE_VALUES': lambda exp, table_values: exp.update({"table_values": unpack_parse_results(table_values)}),
    'ADVANCED_OPTIONS': _pass,  # 125
    'CHANGE_STATUS': _unimplemented,  # implementing # 135
    'COMMENT': _pass,  # implementing? # 40
    'CREATE_NEW_EQUILIBRIUM': _new_equilibrium,  # implementing # 143
    'DEFINE_COMPONENTS': _unimplemented,  # 143
    'ENTER_SYMBOL': _unimplemented,  # implementing #195
    'EVALUATE_FUNCTIONS': _pass,  # 155
    'EXPERIMENT': _unimplemented,  # implementing # 24
    'EXPORT': _pass,  # 26
    'FLUSH_BUFFER': _pass,  # 41
    'IMPORT': _pass,  # 27
    'LABEL_DATA': lambda exp, label: exp.update({"label": label}),  # implementing # 28
    'SAVE_WORKSPACE': _pass,  # 232
    'SET_ALL_START_VALUES': _pass,  # 162
    'SET_ALTERNATE_CONDITION': _pass,  # 30
    'SET_CONDITION': _unimplemented,  # implementing # 165
    'SET_NUMERICAL_LIMITS': _pass,  # 237
    'SET_REFERENCE_STATE': _unimplemented,  # implementing # 169
    'SET_START_VALUE': _unimplemented,  # 171
    'SET_WEIGHT': _pass,  # 33
}

def parsable(instring):
    """
    Return an easily parsable list of strings from an input string.
    """
    lines = instring
    lines = lines.replace('\t', ' ')
    lines = lines.strip()  # strips trailing and leading whitespace
    splitlines = lines.split('\n')  # split by newlines
    splitlines = [' '.join(k.split()) for k in splitlines if k != '']  # separates everything by just one whitespace character
    splitlines = [l for l in splitlines if not (l.startswith("@@") or l.startswith("$"))]
    # Concatenate table values to table end on to one line
    #  very hacky, cannot handle cases where things are in an unexpected order or abbreviated.
    new_splitlines = []
    table_values_line = ''
    capture_values = False
    for line in splitlines:
        if line.startswith('TABLE_VALUE'):
            capture_values = True
            table_values_line = ''.join([table_values_line, line])
        elif line.startswith('TABLE_END'):
            capture_values = False
            table_values_line = ' '.join([table_values_line, line])
            new_splitlines.append(table_values_line)
            table_values_line = ''
        elif capture_values:
            table_values_line = ', '.join([table_values_line, line])
        else:
            new_splitlines.append(line)
    splitlines = new_splitlines
    return splitlines

def main(instring):
    # create an empty
    current_experiment_set = None
    data = [] # a list of dictionaries. New dictionaries are added when a new equilibrium is added.
    commands = parsable(instring)
    for command in commands:
        tokens = None
        try:
            tokens = _pop_grammar().parseString(command)
            new_experiment_set = _POP_PROCESSOR[tokens[0]](current_experiment_set, *tokens[1:])
            # if the new object is different than the old, then we want to make that current and add
            # it to the list of experiments
            if new_experiment_set is not current_experiment_set:
                current_experiment_set = new_experiment_set
                data.append(current_experiment_set)
        except ParseException:
            print("Failed while parsing: " + command)
            print("Tokens: " + str(tokens))
            raise
        except NotImplementedError as e:
            #print("The command {} is not implemented.".format(tokens[0]))
            pass
            #raise NotImplementedError("Command {} is not implemented for tokens {}".format(str(tokens[0]), str(tokens[1:])))
        print(tokens)
        print(command)
    print(data)

try:
    from mgni_test import *
    strs = [mgni_full_str, ca_bi]
    instring = ""
    for s in strs:
        instring = "\n".join([instring, s])
except ImportError:
    print('Failed to import mgni_test. Falling back to last argument to script')
    import sys
    f_arg = sys.argv[-1]
    with open(f_arg, 'r') as f:
        instring = f.read()

if __name__ == "__main__":
    main(instring)

# IMPLEMENTATION STEPS
# 1. Handle the syntax. Be able to parse everything. Start with Mg-Ni
# 2. Get the useful stuff from the parsed data
# 3. Reformat to JSON
