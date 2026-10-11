"""Incremental baseline JPEG coding validator; continuation state never proves image ownership."""
import copy,math
class Invalid(ValueError):pass

class Decoder:
    def __init__(self,raw):
        if raw[:2]!=b'\xff\xd8':raise Invalid('SOI')
        p=2;tables={};frame=None
        while p<len(raw):
            if raw[p]!=255:raise Invalid('header marker')
            while p<len(raw) and raw[p]==255:p+=1
            if p>=len(raw):raise Invalid('short marker')
            marker=raw[p];p+=1
            if p+2>len(raw):raise Invalid('short length')
            n=int.from_bytes(raw[p:p+2],'big');end=p+n
            if n<2 or end>len(raw):raise Invalid('segment bounds')
            data=raw[p+2:end]
            if marker==0xc0:
                if len(data)<6 or data[0]!=8 or len(data)!=6+3*data[5]:raise Invalid('frame')
                frame=(int.from_bytes(data[3:5],'big'),int.from_bytes(data[1:3],'big'),{data[i]:(data[i+1]>>4,data[i+1]&15) for i in range(6,len(data),3)})
            elif marker in (0xc1,0xc2):raise Invalid('nonbaseline')
            elif marker==0xdd and data!=b'\0\0':raise Invalid('restart unsupported')
            elif marker==0xc4:
                q=0
                while q<len(data):
                    if q+17>len(data):raise Invalid('short DHT')
                    key=data[q];counts=data[q+1:q+17];q+=17;table={};code=0
                    for bits,count in enumerate(counts,1):
                        if code+count>1<<bits or q+count>len(data):raise Invalid('DHT bounds')
                        for value in data[q:q+count]:table[bits,code]=value;code+=1
                        q+=count;code<<=1
                    tables[key]=table
            elif marker==0xda:
                if not frame or len(data)<4 or len(data)!=1+2*data[0]+3 or data[-3:]!=b'\0?\0':raise Invalid('scan')
                selectors=[(data[i],data[i+1]>>4,16+(data[i+1]&15)) for i in range(1,len(data)-3,2)]
                if len(selectors)!=len(frame[2]) or {s[0] for s in selectors}!=set(frame[2]):raise Invalid('interleave')
                p=end;break
            p=end
        else:raise Invalid('missing SOS')
        width,height,components=frame
        if not width or not height or width*height>64000000 or any(not h or not v or h>4 or v>4 for h,v in components.values()):raise Invalid('frame bounds')
        mh=max(h for h,v in components.values());mv=max(v for h,v in components.values())
        self.expected=math.ceil(width/(mh*8))*math.ceil(height/(mv*8));self.tables=tables
        self.blocks=tuple(s for s in selectors for _ in range(components[s[0]][0]*components[s[0]][1]))
        if any(k not in tables for s in selectors for k in s[1:]):raise Invalid('missing DHT')
        self.header_end=p;self.mcus=0;self.block=0;self.coefficient=1;self.phase='dc_code';self.code=0;self.code_bits=0
        self.amplitude=0;self.need=0;self.category=0;self.pending_ff=False;self.eoi=False;self.consumed=0;self.predictors={s[0]:0 for s in selectors}
    def clone(self):
        result=copy.copy(self);result.predictors=self.predictors.copy();return result
    def finish_block(self):
        self.block+=1
        if self.block==len(self.blocks):self.block=0;self.mcus+=1
        self.coefficient=1;self.phase='dc_code';self.code=0;self.code_bits=0
    def bit(self,bit):
        if self.phase.endswith('_code'):
            dc=self.phase=='dc_code';key=self.blocks[self.block][1 if dc else 2]
            self.code=(self.code<<1)|bit;self.code_bits+=1;symbol=self.tables[key].get((self.code_bits,self.code))
            if symbol is None:
                if self.code_bits>=16:raise Invalid('Huffman code')
                return
            self.code=0;self.code_bits=0
            if dc:
                if symbol>11:raise Invalid('DC category')
                self.category=symbol;self.need=symbol;self.amplitude=0
                if symbol:self.phase='dc_value'
                else:self.phase='ac_code'
            else:
                run,size=divmod(symbol,16)
                if not size:
                    if not run:self.finish_block();return
                    if run!=15 or self.coefficient+16>64:raise Invalid('AC run')
                    self.coefficient+=16
                    if self.coefficient==64:self.finish_block()
                else:
                    if size>10 or self.coefficient+run>=64:raise Invalid('AC category/run')
                    self.coefficient+=run;self.need=size;self.phase='ac_value'
        elif self.phase=='dc_value':
            self.amplitude=(self.amplitude<<1)|bit;self.need-=1
            if not self.need:
                value=self.amplitude if self.amplitude>=1<<(self.category-1) else self.amplitude-((1<<self.category)-1)
                self.predictors[self.blocks[self.block][0]]+=value;self.phase='ac_code'
        else:
            self.need-=1
            if not self.need:
                self.coefficient+=1
                if self.coefficient==64:self.finish_block()
                else:self.phase='ac_code'
    def feed(self,raw,verify=lambda:None):
        for index,value in enumerate(raw):
            if index%4096==0:verify()
            self.consumed+=1
            if self.eoi:raise Invalid('bytes after EOI')
            if self.pending_ff:
                self.pending_ff=False
                if value==0:
                    if self.mcus==self.expected:raise Invalid('entropy after frame')
                    value=255
                elif value==0xd9 and self.mcus==self.expected:self.eoi=True;continue
                else:raise Invalid('unexpected entropy marker')
            elif value==255:self.pending_ff=True;continue
            elif self.mcus==self.expected:raise Invalid('extra entropy')
            for shift in range(7,-1,-1):
                bit=(value>>shift)&1
                if self.mcus==self.expected:
                    if bit!=1:raise Invalid('nonone pad bit')
                else:self.bit(bit)
        return self
    def signature(self):
        return (self.mcus,self.block,self.coefficient,self.phase,self.code,self.code_bits,self.amplitude,self.need,self.category,self.pending_ff,self.eoi,self.consumed,tuple(self.predictors.items()))
