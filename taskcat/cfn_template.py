from __future__ import absolute_import, unicode_literals

import ruamel.yaml

"""
class CfnTemplate(object):

    def __init__(self):
        self._y = yaml.YAML()
        pass

    def load(self, template):
        return self._y.load(template)

    def dump(self, template):
        stio = io.StringIO()
        self._y.dump(template, stio)
        st = stio.getvalue()
        stio.close()
        return st
"""
typ = 'cfn'


class MyReader(ruamel.yaml.reader.Reader):
    def __init__(self, stream, loader):
        assert stream is None
        assert loader is not None
        ruamel.yaml.reader.Reader.__init__(self, stream, loader)

    @property
    def stream(self):
        return ruamel.yaml.reader.Reader.stream.fget(self)

    @stream.setter
    def stream(self, val):
        if val is None:
            return ruamel.yaml.reader.Reader.stream.fset(self, val)
        s = val.read() if hasattr(val, 'read') else val
        reverse = {}
        md = dict(reverse=reverse)
        setattr(self.loader, '_plug_in_' + typ, md)
        len = 1
        for len in range(1, 10):
            pat = '<' * len + '{'
            if pat not in s:
                s = s.replace('{{', pat)
                reverse[pat] = '{{'
                break
        else:
            raise NotImplementedError('could not find substitute pattern '+pat)
        len = 1
        for len in range(1, 10):
            pat = '#' * len + '%'
            if pat not in s:
                s = s.replace('{%', pat)
                reverse[pat] = '{%'
                break
        else:
            raise NotImplementedError('could not find substitute pattern '+pat)
        return ruamel.yaml.reader.Reader.stream.fset(self, s)


class Rewriter:
    def __init__(self, out, md):
        """store what you need from the metadata"""
        self.reverse = md['reverse']
        self.out = out

    def write(self, data):
        """here the reverse work is done and then written to the original stream"""
        for k in self.reverse:
            data = data.replace(k, self.reverse[k])
        self.out.write(data)


class MyEmitter(ruamel.yaml.emitter.Emitter):
    def __init__(self, *args, **kw):
        assert args[0] is None
        ruamel.yaml.emitter.Emitter.__init__(self, *args, **kw)

    @property
    def stream(self):
        return ruamel.yaml.emitter.Emitter.stream.fget(self)

    @stream.setter
    def stream(self, val):
        if val is None:
            return ruamel.yaml.emitter.Emitter.stream.fset(self, None)
        return ruamel.yaml.emitter.Emitter.stream.fset(self, Rewriter(
            val, getattr(self.dumper, '_plug_in_' + typ)))


def init_typ(self):
    self.Reader = MyReader
    self.Emitter = MyEmitter
    self.Serializer = ruamel.yaml.serializer.Serializer              # type: Any
    self.Representer = ruamel.yaml.representer.RoundTripRepresenter  # type: Any
    self.Scanner = ruamel.yaml.scanner.RoundTripScanner              # type: Any
    self.Parser = ruamel.yaml.parser.RoundTripParser                 # type: Any
    self.Composer = ruamel.yaml.composer.Composer                    # type: Any
    self.Constructor = ruamel.yaml.constructor.RoundTripConstructor  # type: Any