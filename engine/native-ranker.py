"""Research-only native ranking helper; Python remains full-cluster/output authority."""
import pathlib,subprocess,tempfile,time
PHASE={'dc_code':0,'dc_value':1,'ac_code':2,'ac_value':3}
ROOT=pathlib.Path(__file__).resolve().parent

def snapshot(decoder,path,excluded=()):
 d=decoder
 if any(not 0 <= c < 16 for c in d.predictors) or any(not 0 <= key < 32 or not 1 <= bits <= 16 for key,t in d.tables.items() for bits,code in t):
  raise ValueError('Unsupported native JPEG state')
 values=[d.expected,d.mcus,d.block,d.coefficient,PHASE[d.phase],d.code,d.code_bits,d.amplitude,d.need,d.category,int(d.pending_ff),int(d.eoi),d.y_component,d.y_h,d.y_v,d.y_first,d.y_quantization,d.mcu_columns,d.grid.width,d.grid.height,len(d.blocks)]
 for b in d.blocks:values.extend(b)
 values.append(len(d.limits))
 for k,v in d.limits.items():values.extend((k,v))
 values.append(len(d.predictors))
 for k,v in d.predictors.items():values.extend((k,v))
 entries=[(key,bits,code,value) for key,t in d.tables.items() for (bits,code),value in t.items()]
 values.append(len(entries))
 for e in entries:values.extend(e)
 values.extend(d.grid.getdata())
 ranges=[]
 for row in sorted(excluded,key=lambda r:r['offset']):
  a,b=row['offset'],row['offset']+row['bytes']
  if ranges and a<=ranges[-1][1]:ranges[-1][1]=max(b,ranges[-1][1])
  else:ranges.append([a,b])
 values.append(len(ranges))
 for row in ranges:values.extend(row)
 colors=getattr(d,'color_grids',{})
 values.append(len(colors))
 for c,row in colors.items():
  h,v,first,q,grid=row
  values.extend((c,h,v,first,q,grid.width,grid.height))
  values.extend(grid.getdata())
 path.write_text(' '.join(map(str,values))+'\n')

def scan(decoder, fd, first, end, stride, probe, top, seconds, mode='scan', excluded=(), verify=lambda: None):
    import os, math
    binary = ROOT / 'native/jpeg-ranker'
    if not binary.is_file():
        raise FileNotFoundError('Bundled JPEG ranker is missing')
    before = os.fstat(fd)
    identity = lambda st: (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns)
    with tempfile.TemporaryDirectory(prefix='CardMe-ranker-') as directory:
        state = pathlib.Path(directory) / 'state.txt'
        snapshot(decoder, state, excluded)
        command = [str(binary), str(state), '/dev/fd/' + str(fd), str(first), str(end),
                   str(stride), str(probe), str(top), mode]
        deadline = time.monotonic() + seconds
        with subprocess.Popen(command, pass_fds=(fd,), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as process:
            try:
                while True:
                    verify()
                    if time.monotonic() >= deadline:
                        raise subprocess.TimeoutExpired(command, seconds)
                    try:
                        output, errors = process.communicate(timeout=min(.2, max(.001, deadline-time.monotonic())))
                        break
                    except subprocess.TimeoutExpired:
                        continue
                verify()
                if identity(os.fstat(fd)) != identity(before):
                    raise ValueError('Source identity changed during native ranking')
                if process.returncode:
                    raise subprocess.CalledProcessError(process.returncode, command, output, errors)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate()
    if mode == 'single':
        return output.strip().split()
    rows = [(float(score), int(pos)) for score, pos in (line.split() for line in output.splitlines())]
    if len(rows) > top or any(not math.isfinite(score) or pos < first or pos+probe > end or (pos-first)%stride for score,pos in rows):
        raise ValueError('Invalid native ranking output')
    return rows, errors.strip()
