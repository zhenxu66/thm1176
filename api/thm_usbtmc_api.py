'''
Copyright 2018 Hyperfine
Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at
   http://www.apache.org/licenses/LICENSE-2.0
Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
functions
parse_ieee_block_header
from_binary_block
_use_numpy_routines
are copied from pyVISA library
copyright: 2014 by PyVISA Authors, see AUTHORS for more details.
license: MIT, see pyVISA LICENSE for more details.
Interaction with Metrolab's THM1176 field probe based on usbtmc backend
usbtmc preferred over VISA as VISA library has limited availability for Linux. usbtmc is more portable.
VISA preferred on Windows, as use of usbtmc requires manual change of USB driver (libusb instead of standard)
Author: Cedric Hugon
Date: 16Apr2018
'''

import struct
import inspect
import usbtmc
import numpy as np

def _use_numpy_routines(container):
    """Should optimized numpy routines be used to extract the data.
    """
    # Function copied from pyVISA
    # copyright: 2014 by PyVISA Authors, see AUTHORS for more details.
    # license: MIT, see pyVISA LICENSE for more details.
    if np is None or container in (tuple, list):
        return False

    if (container is np.array or (inspect.isclass(container) and
                                  issubclass(container, np.ndarray))):
        return True

    return False


def parse_ieee_block_header(block):
    """
    Parse the header of a IEEE block.
    Definite Length Arbitrary Block:
    #<header_length><data_length><data>
    The header_length specifies the size of the data_length field.
    And the data_length field specifies the size of the data.
    Indefinite Length Arbitrary Block:
    #0<data>
    :param block: IEEE block.
    :type block: bytes | bytearray
    :return: (offset, data_length)
    :rtype: (int, int)
    """
    # Function copied from pyVISA
    # copyright: 2014 by PyVISA Authors, see AUTHORS for more details.
    # license: MIT, see pyVISA LICENSE for more details.


    begin = block.find(b'#')
    if begin < 0:
        raise ValueError("Could not find hash sign (#) indicating the start of"
                         " the block.")

    try:
        # int(block[begin+1]) != int(block[begin+1:begin+2]) in Python 3
        header_length = int(block[begin + 1:begin + 2])
    except ValueError:
        header_length = 0
    offset = begin + 2 + header_length

    if header_length > 0:
        # #3100DATA
        # 012345
        data_length = int(block[begin + 2:offset])
    else:
        # #0DATA
        # 012
        data_length = len(block) - offset - 1

    return offset, data_length


def from_binary_block(block, offset=0, data_length=None, datatype='f',
                      is_big_endian=False, container=list):
    """
    Convert a binary block into an iterable of numbers.
    :param block: binary block.
    :type block: bytes | bytearray
    :param offset: offset at which the data block starts (default=0)
    :param data_length: size in bytes of the data block
                        (default=len(block) - offset)
    :param datatype: the format string for a single element. See struct module.
    :param is_big_endian: boolean indicating endianess.
    :param container: container type to use for the output data.
    :return: items
    :rtype: type(container)
    """
    # Function copied from pyVISA
    # copyright: 2014 by PyVISA Authors, see AUTHORS for more details.
    # license: MIT, see pyVISA LICENSE for more details.

    if data_length is None:
        data_length = len(block) - offset

    element_length = struct.calcsize(datatype)
    array_length = int(data_length / element_length)

    endianess = '>' if is_big_endian else '<'

    if _use_numpy_routines(container):
        return np.frombuffer(block, endianess + datatype, array_length, offset)

    fullfmt = '%s%d%s' % (endianess, array_length, datatype)

    try:
        return container(struct.unpack_from(fullfmt, block, offset))
    except struct.error:
        raise ValueError("Binary data was malformed")


class Thm1176(usbtmc.Instrument):
    ranges = ["0.1T", '0.3T', '1T', '3T']
    trigger_period_bounds = (122e-6, 2.79)
    base_fetch_cmd = ':FETCh:ARRay:'
    axes = ['X', 'Y', 'Z']
    field_axes = ['Bx', 'By', 'Bz']
    fetch_kinds = ['Bx', 'By', 'Bz', 'Timestamp',
                   'Temperature']  # Order matters, this is linked to the fetch command that is sent to retrived data
    n_digits = 5
    defaults = {'block_size': 10, 'period': 0.5, 'range': '0.1T', 'average': 1, 'format': 'INTEGER'}
    id_fields = ['manufacturer', 'model', 'serial', 'version']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.running = False
        self.stop = False

        self.fetch_cmd = None

        self.max_transfer_size = 49216  # (4096 samples * 3 axes * 4B/sample + 64B for time&temp&...
        self.timeout = 10

        self.block_size = self.defaults['block_size']
        self.period = self.defaults['period']
        self.range = self.defaults['range']
        self.average = self.defaults['average']
        self.format = self.defaults['format']

        self.last_reading = {fetch_kind: None for fetch_kind in self.fetch_kinds}
        self.data_stack = {fetch_kind: [] for fetch_kind in self.fetch_kinds}
        self.errors = []

        self.setup(**kwargs)

    def set_format(self):
        self.write(':FORMAT:DATA ' + self.format)

    def set_average(self):

        self.write(':AVERAGE:COUNT {}'.format(self.average))

    def set_range(self):
        '''
        Set sense range of the Metrolab THM1176
        Possible ranges are 0.1T,0.3T,1T,3T
        :param range_str:
        :return:
        '''

        self.write(':SENSe:FLUX:RANGe ' + self.range)

    def set_periodic_trigger(self):
        '''
        Set the probe to run in periodic trigger mode with a given period, continuously
        :param period:
        :return:
        '''
        if self.trigger_period_bounds[0] <= self.period <= self.trigger_period_bounds[1]:
            self.write(':TRIGger:SOURce TIMer')
            self.write(':TRIGger:TIMer {:f}S'.format(self.period))
            self.write(':TRIG:COUNT {}'.format(self.block_size))
            self.write(':INIT:CONTINUOUS ON')
            return True
        else:
            print('Invalid trigger period value.')
            return False

    def str_conv(self, input_str, kind):
        if kind == 'Timestamp':
            val = int(input_str, 0) * 1e-9
            time_offset = val - (self.block_size - 1) * self.period
            res = np.linspace(time_offset, val, self.block_size)
        elif kind == 'Temperature':
            res = int(input_str) * np.ones(self.block_size)

        else:
            res = np.fromstring(input_str.replace('T', ''), sep=',')

        return res

    def parse_ascii_responses(self, kind, res_in):
        '''
        :param kind:
        :return:
        '''
        if kind == 'fetch':
            parsed = res_in.split(';')

            for idx, key in enumerate(self.fetch_kinds):
                self.last_reading[key] = self.str_conv(parsed[idx], key)

            if parsed[-1] == '4':
                res = self.ask(':SYSTEM:ERROR?;*STB?')
                self.errors.append(res)
                while res[0] != '0':
                    print("Error code: {}".format(res))
                    res = self.ask(':SYSTEM:ERROR?;*STB?')
                    self.errors.append(res)

    def parse_binary_responses(self, kind, res_in):

        if kind == 'fetch':
            glob_offset = 0

            for idx, key in enumerate(self.fetch_kinds[:3]):
                offset, length = parse_ieee_block_header(res_in)
                glob_offset += offset
                self.last_reading[key] = from_binary_block(res_in, offset=glob_offset, data_length=length,
                                                           datatype='i', is_big_endian=True, container=np.array)
                glob_offset += length + 4

            glob_offset -= 3  # separation between last binary block and timestamp string is only one byte isntead of 4
            parsed = res_in[glob_offset:].split(b';')
            for idx, key in enumerate(self.fetch_kinds[3:]):
                self.last_reading[key] = self.str_conv(parsed[idx].decode('ascii'), key)

            ending = parsed[-1].decode('ascii')
            if ending.split('\n')[0] == '4':
                res = self.ask(':SYSTEM:ERROR?;*STB?')
                self.errors.append(res)
                while res[0] != '0':
                    print("Error code: {}".format(res))
                    res = self.ask(':SYSTEM:ERROR?;*STB?')
                    self.errors.append(res)

    def get_id(self):
        '''
        Get the identification string of the instrument.
        Parse it according to expected format specified by docs.
        :return:
        '''
        self.write('*IDN?')
        res = self.read()
        id_vals = res.split(',')
        header = {field: val for field, val in zip(self.id_fields, id_vals)}

        return header

    def get_data_array(self):
        '''
        Fetch data from probe buffer
        :return:
        '''
        if self.running:

            if self.format == 'ASCII':
                res = self.ask(self.fetch_cmd)
                self.parse_ascii_responses('fetch', res)

            elif self.format == 'INTEGER':

                self.write(self.fetch_cmd)
                res = self.read_raw()
                self.parse_binary_responses('fetch', res)

    def setup(self, **kwargs):
        '''
        :param kwargs:
        :return:
        '''
        keys = kwargs.keys()

        if 'block_size' in keys:
            self.block_size = kwargs['block_size']

        if 'period' in keys:
            if self.trigger_period_bounds[0] <= kwargs['period'] <= self.trigger_period_bounds[1]:
                self.period = kwargs['period']
            else:
                print('Invalid trigger period value.')
                print('Setting to default...')
                self.period = self.defaults['period']

        if 'range' in keys:
            if kwargs['range'] in self.ranges:
                self.range = kwargs['range']

        if 'average' in keys:
            self.average = kwargs['average']

        if 'format' in keys:
            self.format = kwargs['format']

        self.set_format()
        self.set_range()
        self.set_average()
        self.set_periodic_trigger()

        cmd = ''
        for axis in self.axes:
            cmd += self.base_fetch_cmd + axis + '? {},{};'.format(self.block_size, self.n_digits)
        cmd += ':FETCH:TIMESTAMP?;:FETCH:TEMPERATURE?;*STB?'
        self.fetch_cmd = cmd

    def start_acquisition(self):

        self.running = True
        self.stop = False
        self.write(':INIT')
        while not self.stop:
            self.get_data_array()

            self.data_stack = {key: np.hstack((self.data_stack[key], self.last_reading[key])) for key in
                               self.fetch_kinds}

        self.stop_acquisition()
        self.running = False

    def stop_acquisition(self):

        res = self.ask(':ABORT;*STB?')
        print("Stopping acquisition...")
        print("THM1176 status: {}".format(res))

    def check_error(self):

        res = self.ask(':SYSTEM:ERROR?;*STB?')
        self.errors.append(res)
        while res[0] != '0':
            print("Error code: {}".format(res))
            res = self.ask(':SYSTEM:ERROR?;*STB?')
            self.errors.append(res)