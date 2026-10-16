"""Offline visual differences with explicit environment compatibility and bound sources."""
from paths import Path,save,sha,read
from core import writable,GateError,source
import html,shutil


def compare_images(baseline,candidate,out,environment_a=None,environment_b=None):
    from PIL import Image,ImageChops,ImageStat
    out=writable(out)
    if out.exists():raise FileExistsError(out)
    baseline=Path(baseline).resolve();candidate=Path(candidate).resolve()
    env_a=read(environment_a) if environment_a else None;env_b=read(environment_b) if environment_b else None
    keys={'renderer','version','font_fingerprint','resolution_px'}
    compatible=env_a is not None and env_b is not None and keys<=set(env_a) and keys<=set(env_b) and env_a==env_b
    with Image.open(baseline) as a,Image.open(candidate) as b:
        if a.width*a.height>30000000 or b.width*b.height>30000000:raise GateError('QA_IMAGE_TOO_LARGE')
        def rendered(image):
            rgba=image.convert('RGBA');white=Image.new('RGBA',image.size,(255,255,255,255));return Image.alpha_composite(white,rgba).convert('RGB')
        a=rendered(a);b=rendered(b);same_size=a.size==b.size
        compatible=compatible and env_a['resolution_px']==list(a.size) and env_b['resolution_px']==list(b.size)
        out.mkdir(parents=True)
        a.save(out/'基线.png');b.save(out/'候选.png')
        if same_size:
            diff=ImageChops.difference(a,b);r,g,b=diff.split();mask=ImageChops.lighter(ImageChops.lighter(r,g),b);pixels=diff.width*diff.height-mask.histogram()[0];bbox=diff.getbbox()
            diff.save(out/'像素差.png');rms=ImageStat.Stat(diff).rms
        else:pixels=None;bbox=None;rms=None
    status='INCOMPARABLE_ENVIRONMENT' if not compatible else 'DIFFERENT_DIMENSIONS' if not same_size else 'EXACT_PIXELS_EQUAL' if pixels==0 else 'PIXEL_DIFFERENCES_REQUIRE_REVIEW'
    report=dict(status=status,baseline=source(baseline),candidate=source(candidate),environment_compatible=compatible,
                dimensions_equal=same_size,different_pixels=pixels,difference_bbox=bbox,rms_per_channel=rms,
                environment_a=env_a,environment_b=env_b,semantic_or_scientific_acceptance='NOT_ASSESSED',author_acceptance='PENDING')
    save(out/'图像差异检查.json',report)
    panels=''.join('<figure><img src="'+name+'"><figcaption>'+html.escape(label)+'</figcaption></figure>' for name,label in [('基线.png','基线'),('候选.png','候选')]+([('像素差.png','绝对像素差')] if same_size else []))
    document='<!doctype html><meta charset="utf-8"><title>图像差异检查</title><style>body{font:16px sans-serif;margin:2em;color:#263238}main{display:flex;flex-wrap:wrap;gap:1em}figure{margin:0;max-width:48%}img{width:100%;border:1px solid #ccc}pre{white-space:pre-wrap}</style><h1>图像差异检查</h1><p>'+html.escape(status)+'</p><p>像素比较与科学正确性、原生编辑性、作者接受分别验收。环境不相同时不宣称视觉回归通过。</p><main>'+panels+'</main><pre>'+html.escape(__import__('json').dumps(report,ensure_ascii=False,indent=2))+'</pre>'
    (out/'查看差异.html').write_text(document,encoding='utf-8');return report
