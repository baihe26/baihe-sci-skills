"""Create only this example's new synthetic files; never overwrite an existing file."""
from pathlib import Path
import json, hashlib
from PIL import Image, ImageDraw

root=Path(__file__).resolve().parent
names=['合成面板A.png','合成面板B.png','合成面板C.png','合成面板D.png','合成数值.csv','项目接入.json']
if any((root/name).exists() for name in names):
    raise FileExistsError('已有合成材料，保留原文件；无需重复生成。')
sources=[];panels=[]
for index,letter in enumerate('ABCD'):
    width,height=(1000,500) if index%2 else (800,400)
    image=Image.new('RGB',(width,height),'white');draw=ImageDraw.Draw(image)
    box=[.1+index*.025,.12,.92,.85];l,t,r,b=[int(v*s) for v,s in zip(box,[width,height,width,height])]
    draw.line([(l,t),(l,b),(r,b)],fill='#263238',width=3)
    draw.line([(l,b-20),(l+(r-l)//3,t+(b-t)//2),(r,t+20)],fill='#0072B2',width=4)
    draw.text((12,12),'SYNTHETIC TEST '+letter+' - NOT RESEARCH DATA',fill='black')
    name='合成面板'+letter+'.png';image.save(root/name)
    sources.append(dict(id=letter,path=name,sha256=hashlib.sha256((root/name).read_bytes()).hexdigest(),kind='data_plot',review_status='CONFIRMED'))
    panels.append(dict(id='panel_'+letter,source_id=letter,plot_area_normalized=box,source_font_pt=10,source_width_mm=90))
(root/'合成数值.csv').write_text('synthetic_group,synthetic_value\nA,1\nA,2\nB,3\n',encoding='utf-8')
sources.append(dict(id='synthetic_raw',path='合成数值.csv',kind='numerical_data',review_status='HOLD',
    scientific_metadata=dict(experimental_unit='UNKNOWN',statistical_n='UNKNOWN',uncertainty='UNKNOWN',units='synthetic_units',denominator='not_applicable',design='independent')))
manifest=dict(schema_version='project-intake-0.1',project_id='SYNTHETIC_PANEL_DEMO_NOT_RESEARCH',
    canvas_mm=[180,120],layout_columns=[1,2],minimum_font_pt=7,sources=sources,panels=panels,
    required_figure_ids=['Fig_TEST_1','Fig_TEST_2'],figure_uses=[dict(source_figure_id='Fig_TEST_1',placements=['panel_A','panel_B']),
        dict(source_figure_id='Fig_TEST_2',unused_reason='Synthetic example: deliberately not selected')])
(root/'项目接入.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
