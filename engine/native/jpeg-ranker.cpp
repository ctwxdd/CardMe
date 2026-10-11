// Checkpoint continuation screen. Source opened read-only; Python validates shortlisted full clusters.
#include <array>
#include <vector>
#include <fstream>
#include <iostream>
#include <queue>
#include <cmath>
#include <cstdint>
#include <fcntl.h>
#include <unistd.h>
#include <sys/stat.h>
#include <algorithm>
#include <cstring>
#include <tuple>
#include <future>
#include <thread>
#include <cstdlib>
struct State {int expected,mcus,block,coef,phase,code,bits,amp,need,cat,pending,eoi;std::array<int,16> pred{};double sum=0;int count=0;std::array<double,16> color_sum{};std::array<int,16> color_count{};};
struct Model {int yc,yh,yv,yfirst,q,cols,w,h;std::vector<std::array<int,3>> blocks;std::array<int,16> limits{};std::array<std::vector<int16_t>,32> tables;std::vector<int> grid;struct Color{int h=0,v=0,first=0,q=0,w=0,height=0;std::vector<int> grid;};std::array<Color,16> colors;};
void finish(State&s,const Model&m){if(++s.block==m.blocks.size()){s.block=0;++s.mcus;}s.coef=1;s.phase=0;s.code=s.bits=0;}
bool bit(State&s,const Model&m,int b){int before=s.phase,comp=m.blocks[s.block][0],block=s.block,mcu=s.mcus;
 if(s.phase==0||s.phase==2){bool dc=s.phase==0;int key=m.blocks[s.block][dc?1:2];s.code=(s.code<<1)|b;++s.bits;int symbol=m.tables[key][(1<<s.bits)-1+s.code];
  if(symbol<0)return s.bits<16;
  s.code=s.bits=0;
  if(dc){if(symbol>11)return false;s.cat=s.need=symbol;s.amp=0;s.phase=symbol?1:2;}
  else{int run=symbol/16,size=symbol%16;if(!size){if(!run){finish(s,m);return true;}if(run!=15||s.coef+16>64)return false;s.coef+=16;if(s.coef==64)finish(s,m);}
   else{if(size>10||s.coef+run>=64)return false;s.coef+=run;s.need=size;s.phase=3;}}
 }else if(s.phase==1){s.amp=(s.amp<<1)|b;if(!--s.need){int value=s.amp>=(1<<(s.cat-1))?s.amp:s.amp-((1<<s.cat)-1);s.pred[comp]+=value;s.phase=2;}}
 else{if(!--s.need){if(++s.coef==64)finish(s,m);else s.phase=2;}}
 if((before==0||before==1)&&s.phase==2){int value=s.pred[comp];if(std::abs(value)>m.limits[comp])return false;
  if(m.colors[comp].w){const auto&g=m.colors[comp];int index=block-g.first,x=(mcu%m.cols)*g.h+index%g.h,y=(mcu/m.cols)*g.v+index/g.h;if(x<g.w&&y<g.height){s.color_sum[comp]+=std::abs(value*g.q/8.0+128-g.grid[y*g.w+x]);++s.color_count[comp];}}
  if(comp==m.yc){int index=block-m.yfirst,x=(mcu%m.cols)*m.yh+index%m.yh,y=(mcu/m.cols)*m.yv+index/m.yh;
   if(x<m.w&&y<m.h){s.sum+=std::abs(value*m.q/8.0+128-m.grid[y*m.w+x]);++s.count;}}}
 return true;
}
bool feed(State&s,const Model&m,const unsigned char*raw,size_t n){for(size_t i=0;i<n;++i){int value=raw[i];if(s.eoi)return false;
 if(s.pending){s.pending=0;if(value==0){if(s.mcus==s.expected)return false;value=255;}else if(value==217&&s.mcus==s.expected){s.eoi=1;continue;}else return false;}
 else if(value==255){s.pending=1;continue;}else if(s.mcus==s.expected)return false;
 for(int shift=7;shift>=0;--shift){int b=(value>>shift)&1;if(s.mcus==s.expected){if(b!=1)return false;}else if(!bit(s,m,b))return false;}}
 return true;
}
int main(int argc,char**argv){std::cout.precision(17);if(argc!=9&&argc!=10){std::cerr<<"state source first end stride probe top mode\n";return 2;}State initial;Model m;std::ifstream in(argv[1]);
 in>>initial.expected>>initial.mcus>>initial.block>>initial.coef>>initial.phase>>initial.code>>initial.bits>>initial.amp>>initial.need>>initial.cat>>initial.pending>>initial.eoi;
 in>>m.yc>>m.yh>>m.yv>>m.yfirst>>m.q>>m.cols>>m.w>>m.h;int n,key,value,bits,code;in>>n;m.blocks.resize(n);for(auto&b:m.blocks)in>>b[0]>>b[1]>>b[2];
 in>>n;while(n--){in>>key>>value;m.limits.at(key)=value;}in>>n;while(n--){in>>key>>value;initial.pred.at(key)=value;}
 for(auto&t:m.tables)t.assign(131071,-1);in>>n;while(n--){in>>key>>bits>>code>>value;m.tables.at(key).at((1<<bits)-1+code)=value;}
 if(m.w<=0||m.h<=0||int64_t(m.w)*m.h>1000000)return 3;m.grid.resize(m.w*m.h);for(auto&v:m.grid)in>>v;if(!in)return 4;
 std::vector<std::pair<int64_t,int64_t>> excluded;int ranges=0;if(in>>ranges){while(ranges--){int64_t a,b;in>>a>>b;if(!in||a<0||b<a)return 4;excluded.push_back({a,b});}}std::sort(excluded.begin(),excluded.end());size_t ex=0;int color_n=0;if(in>>color_n){while(color_n--){in>>key;auto&g=m.colors.at(key);in>>g.h>>g.v>>g.first>>g.q>>g.w>>g.height;if(g.w<=0||g.height<=0||int64_t(g.w)*g.height>1000000)return 4;g.grid.resize(g.w*g.height);for(auto&v:g.grid)in>>v;if(!in)return 4;}}
 int fd=open(argv[2],O_RDONLY);if(fd<0)return 5;struct stat before,after;if(fstat(fd,&before))return 6;
 int64_t first=std::stoll(argv[3]),end=std::stoll(argv[4]),stride=std::stoll(argv[5]);int probe=std::stoi(argv[6]),top=std::stoi(argv[7]);
 if(first<0||end>before.st_size||stride<=0||probe<=0||probe>131072||top<1||top>4096)return 7;
 using Row=std::tuple<int,double,int64_t>;
 struct Result {std::priority_queue<Row> heap;int64_t scanned=0,legal=0;bool read_error=false;};
 const std::string mode=argv[8];
 std::vector<int64_t> positions;if(argc==10){std::ifstream list(argv[9]);int64_t p;while(list>>p){if(p<first||p+probe>end||positions.size()>=4096)return 7;positions.push_back(p);}if(!list.eof())return 7;}
 auto search=[&](int64_t begin,int64_t finish)->Result{
  Result result;size_t ex=0;std::vector<unsigned char>raw(probe),previous(probe);bool cached=false,last_ok=false;
  double last_sum=0;int last_count=0;std::array<double,16>last_color_sum{};std::array<int,16>last_color_count{};
  for(int64_t index=begin;index<finish;++index){
   int64_t pos=argc==10?positions[index]:first+index*stride;if(argc==10)ex=0;
   while(ex<excluded.size()&&excluded[ex].second<=pos)++ex;
   if(ex<excluded.size()&&excluded[ex].first<pos+probe)continue;
   if(pread(fd,raw.data(),probe,pos)!=probe){result.read_error=true;return result;}
   State state=initial;++result.scanned;bool ok;
   if(cached&&std::memcmp(raw.data(),previous.data(),probe)==0&&mode!="single"){
    ok=last_ok;state.sum=last_sum;state.count=last_count;state.color_sum=last_color_sum;state.color_count=last_color_count;
   }else{
    ok=feed(state,m,raw.data(),probe);previous=raw;cached=true;last_ok=ok;last_sum=state.sum;last_count=state.count;last_color_sum=state.color_sum;last_color_count=state.color_count;
   }
   if(mode=="single"){
    std::cout<<ok<<" "<<state.count<<" "<<state.sum<<" "<<state.mcus<<" "<<state.block<<" "<<state.coef<<" "<<state.phase<<" "<<state.code<<" "<<state.bits<<" "<<state.amp<<" "<<state.need<<" "<<state.cat<<" "<<state.pending<<" "<<state.eoi;
    for(int v:state.pred)std::cout<<" "<<v;std::cout<<"\n";break;
   }
   if(mode=="shortlist"||mode=="prefix"){
    if(ok&&(state.count||mode=="prefix")){++result.legal;std::cout<<(state.count?state.sum/state.count:0)<<" "<<pos<<"\n";}continue;
   }
   if(ok&&state.count){
    ++result.legal;bool constant=std::all_of(raw.begin()+1,raw.end(),[&](unsigned char v){return v==raw[0];});
    double score=state.sum/state.count;int terms=1;
    for(int c=0;c<16;++c)if(state.color_count[c]){score+=state.color_sum[c]/state.color_count[c];++terms;}
    Row row{constant?1:0,score/terms,pos};
    if(result.heap.size()<top)result.heap.push(row);else if(row<result.heap.top()){result.heap.pop();result.heap.push(row);}
   }
  }return result;
 };
 int64_t count=argc==10?positions.size():(end-first<probe?0:(end-first-probe)/stride+1);
 int workers=1;
 // Only independent ranking probes share the read-only model; joins stay sequential.
 if(mode=="scan"&&S_ISREG(before.st_mode)&&count>=128){
  workers=std::max(1u,std::min(4u,std::thread::hardware_concurrency()));
  if(const char*value=std::getenv("CARDME_RANKER_WORKERS")){
   char*last=nullptr;long requested=std::strtol(value,&last,10);
   if(last!=value&&!*last&&requested>=1&&requested<=4)workers=requested;
  }
 }
 std::vector<std::future<Result>>tasks;
 if(workers>1)for(int i=0;i<workers;++i)tasks.push_back(std::async(std::launch::async,search,count*i/workers,count*(i+1)/workers));
 Result combined;
 for(int i=0;i<workers;++i){
  Result part=workers==1?search(0,count):tasks[i].get();combined.read_error|=part.read_error;
  combined.scanned+=part.scanned;combined.legal+=part.legal;
  while(!part.heap.empty()){
   Row row=part.heap.top();part.heap.pop();
   if(combined.heap.size()<top)combined.heap.push(row);else if(row<combined.heap.top()){combined.heap.pop();combined.heap.push(row);}
  }
 }
 if(combined.read_error){close(fd);return 8;}
 auto&heap=combined.heap;auto scanned=combined.scanned,legal=combined.legal;
 if(fstat(fd,&after)||before.st_dev!=after.st_dev||before.st_ino!=after.st_ino||before.st_size!=after.st_size||before.st_mtimespec.tv_sec!=after.st_mtimespec.tv_sec||before.st_mtimespec.tv_nsec!=after.st_mtimespec.tv_nsec){close(fd);return 9;}
 close(fd);std::vector<Row>rows;while(!heap.empty()){rows.push_back(heap.top());heap.pop();}std::sort(rows.begin(),rows.end());std::cout.precision(17);for(auto r:rows)std::cout<<std::get<1>(r)<<" "<<std::get<2>(r)<<"\n";std::cerr<<"scanned="<<scanned<<" legal="<<legal<<"\n";
}
