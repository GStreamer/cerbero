# Copyright (C) 2024, Fluendo, S.A.
#  Author: Maxim P. Dementiev <dememax@hotmail.com>, Fluendo, S.A.
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Library General Public
# License as published by the Free Software Foundation; either
# version 2 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Library General Public License for more details.
#
# You should have received a copy of the GNU Library General Public
# License along with this library; if not, write to the
# Free Software Foundation, Inc., 59 Temple Place - Suite 330,
# Boston, MA 02111-1307, USA.

import unittest
from cerbero.config import Variants


class ConfigVariantsTest(unittest.TestCase):
    def setUp(self):
        self.variants = Variants([])

    def tearDown(self):
        self.variants = None

    def testReadDefaultValues(self):
        # when nothing was done yet on the new Variants objects, let's check defaults
        self.assertTrue('debug' in dir(self.variants), 'variant is an ordinary object attribute')
        self.assertFalse('nodebug' in dir(self.variants), 'only "no no-prefix" variant is set')
        self.assertTrue(self.variants.debug, 'Debug is enabled by default')
        self.assertFalse(self.variants.nodebug, 'Debug is enabled by default')

        self.assertTrue('alsa' in dir(self.variants))
        self.assertFalse('noalsa' in dir(self.variants))
        self.assertFalse(self.variants.alsa, 'Alsa is disabled by default')
        self.assertTrue(self.variants.noalsa, 'Alsa is disabled by default')
        self.assertFalse(self.variants.uwp)
        self.assertFalse(self.variants.visualstudio)
        self.assertFalse(self.variants.mingw)
        self.assertEqual(self.variants.vscrt, 'md')
        with self.assertRaises(AttributeError):
            self.variants.novscrt  # not bool, no no-* variant

    def testReadDefaultUnknownValues(self):
        with self.assertRaises(AttributeError):
            self.variants.n  # Unknown 1-letter variant name
        self.assertFalse('n' in dir(self.variants), 'After trying to read an non-existant variant')
        with self.assertRaises(AttributeError):
            self.variants.abracadabra  # Unknown long variant name
        self.assertFalse('abracadabra' in dir(self.variants))
        with self.assertRaises(AttributeError):
            self.variants.no  # Tricky: no prefix is used for the logical not
        self.assertFalse('no' in dir(self.variants))

    def testSetWrongName(self):
        with self.assertRaises(AssertionError):
            setattr(self.variants, '-', False)
        with self.assertRaises(AssertionError):
            setattr(self.variants, 'a-', False)
        with self.assertRaises(AssertionError):
            setattr(self.variants, 'a-b', False)

    def testSetKnownVariants(self):
        self.variants.debug = False
        self.assertFalse(self.variants.debug)
        self.assertTrue(self.variants.nodebug, 'for boolean variants it is possible to read no-* variant')
        setattr(self.variants, 'debug', True)
        self.assertTrue(self.variants.debug)
        self.assertFalse(self.variants.nodebug)

    def testSetStringKnownVariants(self):
        self.variants.debug = 'abc'
        self.assertEqual(self.variants.debug, 'abc')
        self.assertEqual(self.variants.nodebug, False, 'for boolean variants it is possible to read no-* variant')
        self.variants.debug = ''
        self.assertEqual(self.variants.debug, '')
        self.assertEqual(self.variants.nodebug, True, 'for boolean variants it is possible to read no-* variant')

    def testSetKnownNoVariants(self):
        # Wrong behaviour?
        self.variants.nodebug = True
        self.assertTrue(self.variants.nodebug)
        self.assertTrue(self.variants.debug, 'is still true: nodebug being set is a different variant')

    def testSetUWP(self):
        self.variants.uwp = False
        self.assertFalse(self.variants.uwp)
        self.assertFalse(self.variants.visualstudio)
        self.assertFalse(self.variants.mingw)
        self.variants.uwp = True
        self.assertTrue(self.variants.uwp)
        self.assertTrue(self.variants.visualstudio)
        self.assertFalse(self.variants.mingw)

    def testSetUnknownVariants(self):
        self.variants.n = False
        self.assertTrue('n' in dir(self.variants), 'after setting an unknown variant, it is an attribute')
        self.assertFalse('non' in dir(self.variants), 'only "no no-prefix" variant is set')
        self.assertFalse(self.variants.n, 'direct read of an variant')
        with self.assertRaises(AttributeError):
            self.assertTrue(self.variants.non, 'for unknown attribute, the no-* variant is not possible')
        self.variants.n = True
        self.assertTrue(self.variants.n)
        with self.assertRaises(AttributeError):
            self.assertFalse(self.variants.non)

        # tricky: 'no'
        self.variants.no = False
        self.assertTrue('no' in dir(self.variants))
        self.assertFalse(self.variants.no)
        with self.assertRaises(AttributeError):
            self.assertTrue(self.variants.nono)

        self.variants.abracadabra = 'nosense'
        self.assertEqual(self.variants.abracadabra, 'nosense')
        with self.assertRaises(AttributeError):
            self.assertFalse(self.variants.noabracadabra, 'for unknown attribute, the no-* variant is not possible')

    def testSetBoolKnownVariants(self):
        self.variants.set_bool('uwp')
        self.assertTrue(self.variants.uwp)
        self.assertFalse(self.variants.nouwp)
        self.variants.set_bool('nouwp')
        self.assertFalse(self.variants.uwp)
        self.assertTrue(self.variants.nouwp)

    def testSetBoolVscrtVariant(self):
        self.variants.set_bool('vscrt')
        self.assertEqual(self.variants.vscrt, True, 'mapping becomes boolean')

    def testSetBoolUnknownVariants(self):
        self.variants.set_bool('n')
        self.assertTrue(self.variants.n)
        with self.assertRaises(AttributeError):
            self.assertFalse(self.variants.non)  # for unknown attribute, the no-* variant is not possible
        self.variants.set_bool('non')
        self.assertFalse(self.variants.n, 'even not boolean variant could be set by no-* variant')

    def testOverrideOneKnownVariant(self):
        self.variants.override('nodebug')
        self.assertFalse(self.variants.debug)
        self.assertTrue(self.variants.nodebug)
        self.variants.override('debug')
        self.assertTrue(self.variants.debug)
        self.assertFalse(self.variants.nodebug)

    def testOverrideKnownVariants(self):
        self.variants.override(['nodebug', 'alsa'])
        self.assertFalse(self.variants.debug)
        self.assertTrue(self.variants.nodebug)
        self.assertTrue(self.variants.alsa)
        self.assertFalse(self.variants.noalsa)

    def testOverrideMappingVariant(self):
        # let's forgot the =value
        self.variants.override('vscrt')
        self.assertEqual(self.variants.vscrt, True, 'mapping becomes boolean')
        with self.assertRaises(AttributeError):
            self.assertFalse(self.variants.novscrt)  # not boolean, no no-* variant

        # with default debug and optimization values
        self.variants.override('vscrt=auto')
        self.assertEqual(self.variants.vscrt, 'md')

        # order in one list is not important for vscrt=auto
        self.variants.override(['debug', 'nooptimization', 'vscrt=auto'])
        self.assertTrue(self.variants.debug)
        self.assertFalse(self.variants.optimization)
        self.assertEqual(self.variants.vscrt, 'mdd')
        self.variants.override(['vscrt=auto', 'nodebug'])
        self.assertFalse(self.variants.debug)
        self.assertFalse(self.variants.optimization)
        self.assertEqual(self.variants.vscrt, 'md')
        self.variants.override('vscrt=auto')
        self.assertFalse(self.variants.debug)
        self.assertFalse(self.variants.optimization)
        self.assertEqual(self.variants.vscrt, 'md')

        # override explicitely
        self.variants.override('vscrt=mdd')
        self.assertEqual(self.variants.vscrt, 'mdd')

        # wrong value
        with self.assertRaises(AttributeError):
            self.variants.override('vscrt=glibc')

        # wrong key
        with self.assertRaises(AttributeError):
            self.variants.override('vs=crt')

    def testOverrideAliasVariants(self):
        self.variants.override('visualstudio')
        self.assertTrue(self.variants.visualstudio)
        self.assertFalse(self.variants.novisualstudio)
        self.assertFalse(self.variants.mingw)
        self.assertTrue(self.variants.nomingw)

        self.variants.override('mingw')
        self.assertFalse(self.variants.visualstudio)
        self.assertTrue(self.variants.novisualstudio)
        self.assertTrue(self.variants.mingw)
        self.assertFalse(self.variants.nomingw)

        # no-* variantes for aliases are not aliases
        self.variants.override('nomingw')
        self.assertFalse(self.variants.visualstudio)
        self.assertTrue(self.variants.novisualstudio)
        self.assertFalse(self.variants.mingw)
        self.assertTrue(self.variants.nomingw)

        # to be or not to be, the order is important
        self.variants.override(['mingw', 'nomingw'])
        self.assertFalse(self.variants.visualstudio)
        self.assertTrue(self.variants.novisualstudio)
        self.assertFalse(self.variants.mingw)
        self.assertTrue(self.variants.nomingw)
        self.variants.override(['novisualstudio', 'visualstudio'])
        self.assertTrue(self.variants.visualstudio)
        self.assertFalse(self.variants.novisualstudio)
        self.assertFalse(self.variants.mingw)
        self.assertTrue(self.variants.nomingw)
