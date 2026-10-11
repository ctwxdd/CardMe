// Research-only checkpoint continuation screen. Source opened read-only; Python validates shortlisted full clusters.
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
int main(int argc,char**argv){std::cout.precision(17);if(argc!=9){std::cerr<<"state source first end stride probe top mode\n";return 2;}State initial;Model m;std::ifstream in(argv[1]);
 in>>initial.expected>>initial.mcus>>initial.block>>initial.coef>>initial.phase>>initial.code>>initial.bits>>initial.amp>>initial.need>>initial.cat>>initial.pending>>initial.eoi;
 in>>m.yc>>m.yh>>m.yv>>m.yfirst>>m.q>>m.cols>>m.w>>m.h;int n,key,value,bits,code;in>>n;m.blocks.resize(n);for(auto&b:m.blocks)in>>b[0]>>b[1]>>b[2];
 in>>n;while(n--){in>>key>>value;m.limits.at(key)=value;}in>>n;while(n--){in>>key>>value;initial.pred.at(key)=value;}
 for(auto&t:m.tables)t.assign(131071,-1);in>>n;while(n--){in>>key>>bits>>code>>value;m.tables.at(key).at((1<<bits)-1+code)=value;}
 if(m.w<=0||m.h<=0||int64_t(m.w)*m.h>1000000)return 3;m.grid.resize(m.w*m.h);for(auto&v:m.grid)in>>v;if(!in)return 4;
 std::vector<std::pair<int64_t,int64_t>> excluded;int ranges=0;if(in>>ranges){while(ranges--){int64_t a,b;in>>a>>b;if(!in||a<0||b<a)return 4;excluded.push_back({a,b});}}std::sort(excluded.begin(),excluded.end());size_t ex=0;int color_n=0;if(in>>color_n){while(color_n--){in>>key;auto&g=m.colors.at(key);in>>g.h>>g.v>>g.first>>g.q>>g.w>>g.height;if(g.w<=0||g.height<=0||int64_t(g.w)*g.height>1000000)return 4;g.grid.resize(g.w*g.height);for(auto&v:g.grid)in>>v;if(!in)return 4;}}
 int fd=open(argv[2],O_RDONLY);if(fd<0)return 5;struct stat before,after;if(fstat(fd,&before))return 6;
 int64_t first=std::stoll(argv[3]),end=std::stoll(argv[4]),stride=std::stoll(argv[5]);int probe=std::stoi(argv[6]),top=std::stoi(argv[7]);
 if(first<0||end>before.st_size||stride<=0||probe<=0||probe>131072||top<1||top>4096)return 7;
 std::vector<unsigned char>raw(probe);using Row=std::tuple<int,double,int64_t>;std::priority_queue<Row>heap;int64_t scanned=0,legal=0;std::vector<unsigned char> previous(probe);bool cached=false,last_ok=false;double last_sum=0;int last_count=0;std::array<double,16> last_color_sum{};std::array<int,16> last_color_count{};
 for(int64_t pos=first;pos+probe<=end;pos+=stride){while(ex<excluded.size()&&excluded[ex].second<=pos)++ex;if(ex<excluded.size()&&excluded[ex].first<pos+probe)continue;ssize_t got=pread(fd,raw.data(),probe,pos);if(got!=probe){close(fd);return 8;}State s=initial;++scanned;
  bool ok; if(cached&&std::memcmp(raw.data(),previous.data(),probe)==0&&std::string(argv[8])!="single"){ok=last_ok;s.sum=last_sum;s.count=last_count;s.color_sum=last_color_sum;s.color_count=last_color_count;}else{ok=feed(s,m,raw.data(),probe);previous=raw;cached=true;last_ok=ok;last_sum=s.sum;last_count=s.count;last_color_sum=s.color_sum;last_color_count=s.color_count;}if(std::string(argv[8])=="single"){std::cout<<ok<<" "<<s.count<<" "<<s.sum<<" "<<s.mcus<<" "<<s.block<<" "<<s.coef<<" "<<s.phase<<" "<<s.code<<" "<<s.bits<<" "<<s.amp<<" "<<s.need<<" "<<s.cat<<" "<<s.pending<<" "<<s.eoi;for(int v:s.pred)std::cout<<" "<<v;std::cout<<"\n";break;}
  if(ok&&s.count){++legal;bool constant=std::all_of(raw.begin()+1,raw.end(),[&](unsigned char v){return v==raw[0];});double score=s.sum/s.count;int terms=1;for(int c=0;c<16;++c)if(s.color_count[c]){score+=s.color_sum[c]/s.color_count[c];++terms;}Row r{constant?1:0,score/terms,pos};if(heap.size()<top)heap.push(r);else if(r<heap.top()){heap.pop();heap.push(r);}}}
 if(fstat(fd,&after)||before.st_dev!=after.st_dev||before.st_ino!=after.st_ino||before.st_size!=after.st_size||before.st_mtimespec.tv_sec!=after.st_mtimespec.tv_sec||before.st_mtimespec.tv_nsec!=after.st_mtimespec.tv_nsec){close(fd);return 9;}
 close(fd);std::vector<Row>rows;while(!heap.empty()){rows.push_back(heap.top());heap.pop();}std::sort(rows.begin(),rows.end());std::cout.precision(17);for(auto r:rows)std::cout<<std::get<1>(r)<<" "<<std::get<2>(r)<<"\n";std::cerr<<"scanned="<<scanned<<" legal="<<legal<<"\n";
}
