##
## This file is part of the libsigrokdecode project.
##
## Copyright (C) 2020 Kari Hautio <khautio@gmail.com>
##
## This program is free software; you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published by
## the Free Software Foundation; either version 3 of the License, or
## (at your option) any later version.
##
## This program is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with this program; if not, see <http://www.gnu.org/licenses/>.
##

import sigrokdecode as srd

# some constants for protocol
TAIL_FIRST = 0x80
TAIL_LAST = 0x40
TAIL_TOGGLE = 0x20
TAIL_IDMASK = 0x1f

class Decoder(srd.Decoder):
    api_version = 3
    id = 'uavcan'
    name = 'UAVCAN'
    longname = 'UAVCAN protocol decoder'
    desc = 'UAVCAN parser for CAN'
    license = 'gplv3+'
    inputs = ['can']
    outputs = []
    tags = ['Util']
    options = (
    )
    annotations = (
        ('bits', 'UAVCAN bits'),
        ('frames', 'UAVCAN frames'),
        ('errors', 'Error information'),
    )

    def __init__(self):
        self.reset()

    def putb(self, data):
        self.put(self.ss,self.es,self.out_ann,data)

    def clearmf(self):
        self.mfss = None
        self.mfcrc = None
        self.mfpayload = None
        self.mftoggle = None
        self.mfid = None

    def reset(self):
        self.clearmf()

    def start(self):
        self.out_ann = self.register(srd.OUTPUT_ANN)
    
    def printuavcanframe(self, sid, prio, mtid, payload):
        self.putb([1, ['frame: S %d P %d ID %d %s' % (sid, prio, mtid, payload)]])

    def message(self, sid, prio, mtid, payload):
        tailbyte = payload[-1]
        if (tailbyte & (TAIL_FIRST | TAIL_LAST)) == (TAIL_FIRST | TAIL_LAST):
            if (tailbyte & TAIL_TOGGLE):
                self.putb([2, ['single frame with toggle=1 S %d P %d ID %d %x' % (sid, prio, mtid, tailbyte)]])
            self.printuavcanframe(sid, prio, mtid, payload[0:-1])
            
        elif (tailbyte & (TAIL_FIRST | TAIL_LAST)) == TAIL_FIRST:
            if (self.mfpayload):
                self.putb([2, ['first overwrite S %d P %d ID %d %x' % (sid, prio, mtid, tailbyte)]])
            if (tailbyte & TAIL_TOGGLE):
                self.putb([2, ['first frame with toggle=1 S %d P %d ID %d %x' % (sid, prio, mtid, tailbyte)]])
                return
            self.mfss = self.ss
            self.mftoggle = TAIL_TOGGLE
            self.mfid = (tailbyte & TAIL_IDMASK)
            self.mfcrc = payload[0:1]
            self.mfpayload = payload[2:6]
        else: # either mid or last frame of multiframe transfer
            if self.mfpayload == None:
                self.putb([2, ['no first frame S %d P %d ID %d %x' % (sid, prio, mtid, tailbyte)]])
                return
            if (tailbyte & TAIL_TOGGLE) != self.mftoggle:
                self.putb([2, ['invalid toggle S %d P %d ID %d %x' % (sid, prio, mtid, tailbyte)]])
                self.clearmf()
                return
            self.mftoggle ^= TAIL_TOGGLE
            if (tailbyte & TAIL_IDMASK) != self.mfid:
                self.putb([2, ['invalid mfid S %d P %d ID %d %x' % (sid, prio, mtid, tailbyte)]])
                self.clearmf()
                return
            if (tailbyte & (TAIL_FIRST | TAIL_LAST)) == TAIL_LAST: # last frame of multiframe transfer
                self.mfpayload.extend(payload[0:-1])
                self.printuavcanframe(sid, prio, mtid, self.mfpayload)
                self.clearmf()
            else:
                self.mfpayload.extend(payload[0:-1])

    def decode(self, ss, es, data):
        frame_type, fullid, rtr_type, dlc, payload = data

        if frame_type != 'extended':
            return # UAVCAN only uses extended frames

        self.ss, self.es = ss, es

        priority = (fullid & (0x1f <<24)) >> 24
        sid = (fullid & 0x7f)
        service_not_message = (fullid & (1 << 7)) >> 7

        if service_not_message:
            did =  (fullid & (0x7f << 8)) >> 8
            rnr = (fullid & (1 << 15)) >> 15
            sti =      (fullid & (0xff << 16)) >> 16
            self.putb([2, ['TODO: service p %d stid %d r %d, D %d S %d' %
                           (priority, sti, rnr, did, sid)]])
        elif sid == 0:
            mtid = (fullid & (0x3 << 8)) >> 8
            disc = (fullid & (0x3fff << 10)) >> 10
            self.putb([2, ['TODO: anon msg S: %d ID: %d Disc: %d' %
                           (sid, mtid, disc)]])
        else:
            mtid = (fullid & (0xffff << 8)) >> 8
            if payload:
                self.message(sid, priority, mtid, payload)
            else:
                self.putb([2, ['no payload  S: %d ID: %d' %
                           (sid, mtid)]])
            
