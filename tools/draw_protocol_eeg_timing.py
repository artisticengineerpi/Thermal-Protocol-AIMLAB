"""Minimal block sequence and color-coded Latin square."""
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

root = Path(__file__).resolve().parents[1]
out = root/'reference/protocol-picture'
out.mkdir(parents=True, exist_ok=True)
plt.rcParams.update({'font.family':'DejaVu Sans','svg.fonttype':'none'})
fig=plt.figure(figsize=(14,9.2),facecolor='white')
ax=fig.add_axes([0,0,1,1],xlim=(0,1400),ylim=(920,0))
ax.axis('off')
colors={'A':'#707987','B':'#CB661F','C':'#178D80','D':'#8555BC'}
fills={'A':'#E9EDF2','B':'#FFE7D5','C':'#DDF4EE','D':'#EEE3FA'}

def text(x,y,s,size=18,bold=False,ha='left'):
    ax.text(x,y,s,fontsize=size,color='black',ha=ha,va='center',
            fontweight='bold' if bold else 'normal')
def box(x,y,w,h,edge='#777777',fill='white',lw=1.2):
    ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0,rounding_size=12',
                               edgecolor=edge,facecolor=fill,linewidth=lw))
def arrow(x1,y,x2):
    ax.annotate('',xy=(x2,y),xytext=(x1,y),arrowprops={'arrowstyle':'->','lw':1.6,'color':'black'})

text(65,60,'EXPERIMENT BLOCKS + LATIN SQUARE',26,True)
text(65,115,'5 blocks × 32 trials = 160 trials',18)
text(1330,115,'≈40–45 min total',20,True,'right')
for i in range(5):
    x=65+i*260
    box(x,161,225,100)
    text(x+112.5,196,f'BLOCK {i+1}',18,True,'center')
    text(x+112.5,223,'32 trials',15,ha='center')
    text(x+112.5,248,'≈5 min',11,ha='center')
    if i<4: arrow(x+233,211,x+252)
text(700,302,'Breaks: 1 min',16,ha='center')

text(65,385,'IN EACH BLOCK',20,True)
text(65,423,'Read rows in order. Repeat the square twice total.',16)
rows=['ABDC','BCAD','CDBA','DACB']
for r,row in enumerate(rows):
    y=467+r*66
    text(81,y+27,str(r+1),15,ha='center')
    for c,letter in enumerate(row):
        x=112+c*109
        box(x,y,91,54,colors[letter],fills[letter],1.7)
        text(x+45.5,y+27,letter,23,True,'center')
text(330,761,'16 trials × 2 = 32 trials',17,True,'center')

text(785,385,'STIMULUS TYPES',20,True)
for i,(letter,label) in enumerate([('A','No stimulation'),('B','Thermal only'),
                                  ('C','Vibration only'),('D','Thermal + vibration')]):
    y=467+i*66
    box(785,y,61,54,colors[letter],fills[letter],1.7)
    text(815.5,y+27,letter,21,True,'center')
    text(872,y+27,label,18)

ax.plot([65,1330],[805,805],color='#BBBBBB',lw=1)
for x,label,value in [(65,'EEG gel','15 min'),(535,'Experiment','≈25–30 min'),(1005,'Total','≈40–45 min')]:
    text(x,844,label,17)
    text(x,885,value,22,True)

fig.savefig(out/'experiment-blocks-eeg-timing.png',dpi=300,facecolor='white')
fig.savefig(out/'experiment-blocks-eeg-timing.svg',facecolor='white')
fig.savefig(out/'experiment-blocks-eeg-timing-preview.png',dpi=100,facecolor='white')
print(out/'experiment-blocks-eeg-timing.png')
