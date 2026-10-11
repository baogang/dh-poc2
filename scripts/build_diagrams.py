"""diagram-design default light doc-wide SVG/HTML; fixed geometry and accessible figures."""
from pathlib import Path
from html import escape

PAPER='#f5f5f5';INK='#2d3142';MUTED='#4f5d75';ACCENT='#eb6c36';LINK='#2e5aa8'


def start(slug,title,desc):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" role="img" aria-labelledby="{slug}-title {slug}-desc">
<title id="{slug}-title">{escape(title)}</title><desc id="{slug}-desc">{escape(desc)}</desc>
<defs><marker id="arrow" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto"><polygon points="0 0,8 3,0 6" fill="{MUTED}"/></marker>
<marker id="arrow-accent" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto"><polygon points="0 0,8 3,0 6" fill="{ACCENT}"/></marker>
<marker id="arrow-link" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto"><polygon points="0 0,8 3,0 6" fill="{LINK}"/></marker>
<marker id="arrow-open" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto"><polyline points="0 0,8 3,0 6" fill="none" stroke="{MUTED}" stroke-width="1.2"/></marker></defs>
<rect width="1280" height="720" fill="{PAPER}"/>
<text x="40" y="44" fill="{MUTED}" font-size="12" class="mono">DH / SPEECH GATEWAY / V1</text>
<text x="40" y="88" fill="{INK}" font-size="28" font-weight="600">{escape(title)}</text>'''


def text(x,y,t,size=12,anchor='start',color=MUTED):
    return f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" text-anchor="{anchor}">{escape(t)}</text>'


def node(x,y,w,h,title,sub,tag='SVC',focus=False,dash=False):
    c=ACCENT if focus else MUTED
    dashed='stroke-dasharray="5,4"' if dash else ''
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="{PAPER}"/><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="{PAPER}" stroke="{c}" {dashed}/><rect x="{x+12}" y="{y+8}" width="44" height="20" rx="2" fill="{PAPER}" stroke="{c}" opacity=".6"/>'+text(x+34,y+23,tag,10,'middle',c)+text(x+w/2,y+h/2+6,title,16,'middle',INK)+text(x+w/2,y+h/2+28,sub,12,'middle')


def edge(d,color=MUTED,dash=False,open_head=False):
    marker='arrow-open' if open_head else ('arrow-accent' if color==ACCENT else 'arrow-link' if color==LINK else 'arrow')
    return f'<path d="{d}" fill="none" stroke="{color}" stroke-width="1.5" '+('stroke-dasharray="5,4"' if dash else '')+f' marker-end="url(#{marker})"/>'


def label(x,y,width,t):
    # y is connector y. Mask ends 8px above the line.
    return f'<rect x="{x-width/2}" y="{y-28}" width="{width}" height="20" rx="2" fill="{PAPER}"/>'+text(x,y-13,t,12,'middle')


def finish(svg,legend):
    return svg+'<line x1="40" y1="668" x2="1240" y2="668" stroke="#2d3142" opacity=".12"/>'+text(40,696,legend)+ '</svg>'


def save(slug,svg):
    out=Path('docs/diagrams');out.mkdir(parents=True,exist_ok=True)
    html=f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>{slug}</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:{PAPER};color:{INK};font-family:Geist,"Noto Sans SC","PingFang SC","Microsoft YaHei",system-ui,sans-serif}}figure{{margin:0;overflow-x:auto}}svg{{display:block;width:100%;min-width:1280px;height:auto}}.mono{{font-family:"Geist Mono",Menlo,monospace}}@media print{{svg{{min-width:0;width:100%}}figure{{overflow:visible}}@page{{size:A4 landscape;margin:12mm}}}}
</style></head><body><figure>{svg}</figure></body></html>'''
    (out/(slug+'.html')).write_text(html)


def overview():
    s=start('overview','网站与 Genesys 共用语音服务','网站和Genesys通过同一个Gateway调用ASR、业务Agent和TTS，Avatar运行时仅预留。')
    s+=text(40,124,'13个当前逻辑模块按职责聚合；部署组件数量与逻辑模块数量不同。')
    # Connectors before opaque nodes. No connector crosses another.
    s+=edge('M 260 252 H 280 Q 288 252 288 260 V 320 Q 288 328 296 328 H 352',LINK)
    s+=edge('M 260 444 H 312 Q 320 444 320 436 V 384 Q 320 376 328 376 H 352',LINK)
    s+=edge('M 592 328 H 648 Q 656 328 656 320 V 232 Q 656 224 664 224 H 720')
    s+=edge('M 720 248 H 696 Q 688 248 688 256 V 336 Q 688 344 680 344 H 592',dash=True)
    s+=edge('M 592 360 H 1016',LINK)
    s+=edge('M 1016 376 H 592',LINK,dash=True)
    s+=edge('M 592 392 H 632 Q 640 392 640 400 V 432 Q 640 440 648 440 H 720')
    s+=edge('M 720 476 H 556 Q 548 476 548 468 V 404',dash=True)
    s+=edge('M 472 404 V 536')
    s+=edge('M 812 504 V 628 Q 812 636 820 636 H 1108 Q 1116 636 1116 628 V 616',dash=True)
    s+=node(80,208,180,88,'网站语音','M01 · 双向PCM16',tag='WEB')
    s+=node(80,400,180,88,'Genesys IVR','M02 · 双向PCMU',tag='IVR')
    s+=node(352,300,240,104,'Speech Gateway','M03/04/05/07/09/11',focus=True)
    s+=node(720,180,180,88,'ASR 服务','M06 · Qwen / Nemotron')
    s+=node(1016,300,180,88,'业务 Agent','M08 · HiAgent 接口',tag='API')
    s+=node(720,416,180,88,'TTS 服务','M10 · VoxCPM2')
    s+=node(352,536,240,80,'状态与观测','M12/M13 · SQLite/评估',tag='OPS')
    s+=node(1016,536,180,80,'Avatar Runtime','M14 · 后续专项',tag='NEXT',dash=True)
    s+=text(80,640,'PoC不启用LiveKit；未来媒体服务通过通道接口接入。')
    save('overview',finish(s,'实线：请求；虚线：返回/未来接口；蓝色：外部接口。Gateway调用所有服务；音频由原通道返回。'))


def interruption():
    s=start('interruption','打断必须同时停止服务端与终端播放','用户起音后Gateway增加epoch、取消旧合成并通知终端清空队列；迟到旧音频丢弃。')
    s+=text(40,124,'每个会话由一个协调器写入音频；取消不是旧任务已停止的证明。')
    for x in [180,480,1040]:s+=f'<line x1="{x}" y1="188" x2="{x}" y2="656" stroke="{MUTED}" opacity=".25" stroke-dasharray="3,3"/>'
    s+=edge('M 480 204 H 1040',LINK)+label(760,204,224,'合成请求 · epoch 7')
    s+=edge('M 1040 264 H 480',dash=True)+label(760,264,224,'返回音频 · epoch 7')
    s+=edge('M 480 324 H 180')+label(330,324,208,'播放音频 · epoch 7')
    s+=edge('M 180 380 H 480',dash=True,open_head=True)+label(330,380,208,'用户起音 · VAD事件')
    s+=edge('M 480 412 H 540 Q 548 412 548 420 V 432 Q 548 440 540 440 H 480',ACCENT)
    s+=f'<rect x="556" y="416" width="204" height="20" fill="{PAPER}"/>'+text(560,431,'epoch 8；旧输出失效')
    s+=edge('M 480 476 H 1040',dash=True,open_head=True)+label(760,476,208,'取消旧合成 · epoch 7')
    s+=edge('M 480 520 H 180',dash=True,open_head=True)+label(330,520,208,'STOP 8 · 清空队列')
    s+='<rect x="448" y="544" width="624" height="112" rx="4" fill="rgba(45,49,66,.02)" stroke="#2d3142" opacity=".65"/>'
    s+=f'<rect x="448" y="544" width="44" height="20" rx="2" fill="{PAPER}" stroke="{MUTED}"/>'+text(470,559,'OPT',12,'middle')
    s+=text(504,566,'[旧任务忽略取消，仍有迟到音频]')
    s+=edge('M 1040 604 H 480',dash=True,open_head=True)+label(760,604,200,'迟到音频 · epoch 7')
    s+=edge('M 480 624 H 540 Q 548 624 548 632 V 640 Q 548 648 540 648 H 480')
    s+=f'<rect x="556" y="624" width="240" height="20" fill="{PAPER}"/>'+text(560,639,'7 ≠ 8，丢弃；不得继续播放')
    for x,title in [(80,'网站 / Genesys'),(380,'Gateway'),(940,'TTS 服务')]:
        s+=f'<rect x="{x}" y="140" width="200" height="48" rx="6" fill="{PAPER}" stroke="{MUTED}"/>'+text(x+100,170,title,16,'middle',INK)
    save('interruption',finish(s,'虚线实心头：返回；虚线空心头：单向事件。stop 后还需检查浏览器队列与Genesys播放反馈。'))


def deployment():
    s=start('deployment','3000 calls/h 是到达率，不是并发数','5分钟平均通话时长对应250平均并发、500两倍峰值；Gateway和模型池独立扩展，GPU数量需压测。')
    s+=text(40,124,'暂定：AHT 300s × 3000/3600 = 250路；2倍峰值 = 500路；网站负载另计。')
    for x,w,title in [(40,248,'外部通道'),(312,216,'入口边界'),(552,688,'私有运行环境')]:
        s+=f'<rect x="{x}" y="164" width="{w}" height="472" rx="6" fill="none" stroke="{MUTED}" stroke-dasharray="4,4" opacity=".4"/>'+text(x+16,192,title,14)
    s+=edge('M 256 360 H 336',LINK)+edge('M 504 360 H 624')
    s+=edge('M 864 336 H 896 Q 904 336 904 328 V 276 Q 904 268 912 268 H 936')
    s+=edge('M 864 384 H 896 Q 904 384 904 392 V 468 Q 904 476 912 476 H 936')
    s+=edge('M 744 404 V 536')
    s+=node(72,316,184,88,'Genesys + 网站','电话峰值500；网站另计',tag='IN')
    s+=node(336,316,168,88,'接入认证 / TLS','签名与准入',tag='EDGE')
    s+=node(624,300,240,104,'Gateway 副本池','每Pod有界会话/任务',focus=True)
    s+=node(936,224,256,88,'ASR 独立池','35%假设 → 175活跃等效',tag='GPU')
    s+=node(936,432,256,88,'TTS 独立池','25%假设 → 125活跃等效',tag='GPU')
    s+=node(624,536,240,80,'状态与观测','生产共享；PoC本地',tag='OPS')
    s+=text(584,224,'扩展先测：每GPU吞吐、会话缓存、显存与P95首音频。')
    s+=text(936,580,'GPU数量按实测计算；此图不承诺500路达标。')
    save('deployment',finish(s,'Gateway按连接/CPU扩容，ASR/TTS按模型负载扩容；利用率目标、故障余量和真实回合占比需共同验收。'))

if __name__=='__main__':
    overview();interruption();deployment()
