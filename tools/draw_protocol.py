"""Render the exact study protocol as a printable, deterministic diagram."""
from pathlib import Path
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Polygon

ROOT = Path(__file__).resolve().parents[1]
cfg = json.loads((ROOT/'study.json').read_text())
OUT = ROOT/'reference'/'protocol-picture'
OUT.mkdir(parents=True, exist_ok=True)
plt.rcParams.update({'font.family':'DejaVu Sans', 'svg.fonttype':'none'})
fig = plt.figure(figsize=(16,13.6), facecolor='#000000')
ax = fig.add_axes([0,0,1,1], xlim=(0,1600), ylim=(1360,0), facecolor='#000000')
ax.axis('off')
WHITE='#FFFFFF'; GREY='#B8BDC5'; EDGE='#656A72'

def text(x,y,s,size=15,bold=False,color=WHITE,ha='left'):
    ax.text(x,y,s,fontsize=size,color=color,ha=ha,va='center',
            fontweight='bold' if bold else 'normal',linespacing=1.4)

def box(x,y,w,h,edge=EDGE,fill='#080808'):
    ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0,rounding_size=10',
                              linewidth=1,edgecolor=edge,facecolor=fill))

def arrow(x1,y1,x2,y2):
    ax.annotate('',xy=(x2,y2),xytext=(x1,y1),
                arrowprops={'arrowstyle':'->','color':WHITE,'lw':1.5})

def heading(x,y,n,label):
    text(x,y,n,14,color=GREY)
    text(x+39,y,label,18,True)

text(60,55,'AIMLAB / EXPERIMENT MAP',27,True)
text(1540,55,'160 trials  ·  5 blocks  ·  No EEG',17,ha='right')
text(60,108,f"DEFAULTS   Motors {cfg['initial_motor_pwm']} PWM  ·  Peltier HOT {cfg['thermal_pwm']} PWM  ·  Motion 4.0 s  ·  Lead 980 ms",16,color=GREY)
heading(60,157,'01','SET UP')
cards=[('Connect Uno','Wait for CONNECTED'),('Test sleeve + cues','M1–M4 · Thermal · Combined'),
       ('Calibrate','Motor 0–255 · Lead 0–2000 ms'),('Save + lock','Space to begin')]
for i,(title,sub) in enumerate(cards):
    x=60+i*385
    box(x,187,325,76)
    text(x+162.5,213,title,17,True,ha='center')
    text(x+162.5,241,sub,12,ha='center',color=GREY)
    if i<3: arrow(x+337,225,x+374,225)

heading(60,315,'02','ONE TRIAL')
steps=[('Fixation cross','500 Hz beep · random 3–4.5 s'),
       ('Run condition A, B, C or D','1000 Hz beep · black screen*'),
       ('Confirm all outputs OFF','Wait for the Uno'),
       ('Show question','500 Hz beep · wait 1 s'),
       ('Answer → save → next trial','Keys 1–5 · no time limit')]
for i,(title,sub) in enumerate(steps):
    y=352+i*77
    box(60,y,580,61)
    text(83,y+22,title,16,True)
    text(83,y+45,sub,12,color=GREY)
    if i<4: arrow(350,y+64,350,y+75)
text(60,753,'*White status and STOP controls remain visible.',11,color=GREY)

heading(705,315,'03','LATIN SQUARE + CONDITION KEY')
rows=['ABDC','BCAD','CDBA','DACB']
for r,row in enumerate(rows):
    y=362+r*74
    text(714,y+31,f'{r*4+1:02d}–{r*4+4:02d}',12,color=GREY)
    for c,letter in enumerate(row):
        x=783+c*70
        box(x,y,59,61,edge='#A6ABB2')
        text(x+29.5,y+31,letter,23,True,ha='center')
legend=[('A','No stimulation','5 s'),('B','Thermal only','5 s'),
        ('C','Moving vibration','4 s'),('D','Combined','lead + 4 s')]
for i,(letter,name,duration) in enumerate(legend):
    y=386+i*74
    text(1135,y,letter,21,True)
    text(1180,y,name,16,True)
    text(1180,y+27,duration,13,color=GREY)
text(705,691,'Read each row left → right, then move down.',15)
text(705,725,'Repeat all 4 rows once = 32 trials per block.',15,True)
text(705,753,'Same order in every block; seed varies fixation only.',11,color=GREY)

heading(60,811,'04','FIVE BLOCKS')
for i in range(5):
    x=60+i*302
    box(x,846,270,82)
    text(x+135,873,f'BLOCK {i+1}',16,True,ha='center')
    text(x+135,903,f'Trials {i*32+1}–{(i+1)*32}',14,ha='center',color=GREY)
    if i<4: arrow(x+276,887,x+297,887)
text(60,956,'Between blocks: 60 s break → Space',15)
text(1540,956,'32 × 5 = 160 trials  ·  40 per condition',15,True,ha='right')

heading(60,1012,'05','COMBINED TIMING')
text(60,1043,'Default lead shown: 0.98 s. Motor motion stays 4 s.',12,color=GREY)
x0=185; scale=137
def tx(t): return x0+t*scale
lead=cfg['initial_lead_ms']/1000
end=lead+4
text(65,1090,'Peltier',13)
box(tx(.05),1078,(end-.05)*scale,20,edge=WHITE,fill='#444444')
for i in range(4):
    baseline=1140+i*34
    start=lead+i*.8
    text(65,baseline-8,f'M{i+1}',13)
    ax.add_patch(Polygon([(tx(start),baseline),(tx(start+.4),baseline-20),
                          (tx(start+1.2),baseline-20),(tx(start+1.6),baseline)],
                         closed=True,facecolor='#393939',edgecolor=WHITE,linewidth=1.2))
ax.plot([tx(lead),tx(lead)],[1070,1255],color=GREY,lw=.8,ls=':')
ax.plot([tx(end),tx(end)],[1070,1255],color=GREY,lw=.8,ls=':')
for t in range(6): text(tx(t),1261,str(t),11,ha='center',color=GREY)
text(910,1261,'s',11,color=GREY)
text(60,1294,'SOA 0.8 s  ·  Each motor ON envelope 1.6 s',12)
text(60,1320,'Heat starts 50 ms after RUN; stops with the last motor.',11,color=GREY)

heading(1040,1012,'06','RESPONSE KEY')
for i,label in enumerate(['No sensation','Static heat','Moving vibration','Moving heat','Not sure'],1):
    text(1044,1059+(i-1)*34,str(i),16,True)
    text(1083,1059+(i-1)*34,label,15)
text(1040,1246,'STOP EXPERIMENT / Esc → OFF + pause',12,True)
text(1040,1275,'Lost link → reconnect → Space retries trial',11)
text(1040,1310,'PWM is not measured temperature.',11,color=GREY)

fig.savefig(OUT/'experiment-map.png',dpi=300,facecolor=fig.get_facecolor())
fig.savefig(OUT/'experiment-map.svg',facecolor=fig.get_facecolor())
fig.savefig(OUT/'experiment-map-preview.png',dpi=100,facecolor=fig.get_facecolor())
print(OUT/'experiment-map.png')
