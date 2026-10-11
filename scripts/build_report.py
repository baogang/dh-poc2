"""Recompute aggregates, failures and availability; never publish SADA transcripts."""
import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np
from speech_gateway.metrics import normalize


def optional(path):
    return json.loads(path.read_text()) if path.exists() else None


def percent(value):
    return f'{value:.2%}' if value is not None else '未取得'


def seconds(value):
    return f'{value:.2f}' if value is not None else '未取得'


def generate(raw, out, manifest_path):
    raw, out = Path(raw), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    rows=optional(raw/'asr.json')
    manifest=optional(Path(manifest_path))
    groups=defaultdict(list)
    for row in rows or []:
        groups[(row['model'],row['condition'])].append(row)
    summary=[]
    for (model,condition),items in sorted(groups.items()):
        good=[x for x in items if 'scores' in x and x.get('status')==200]
        record={'model':model,'condition':condition,'successful':len(good),'attempted':len(items),'failed':len(items)-len(good)}
        for metric in ['wer','cer','strict_wer']:
            units=sum(x['scores'][metric]['reference_units'] for x in good)
            errors=sum(sum(x['scores'][metric][k] for k in ['substitutions','deletions','insertions']) for x in good)
            record[metric]={'units':units,'errors':errors,'rate':errors/units if units else None}
        times=[x['elapsed_seconds'] for x in good]
        record['latency_seconds']={f'p{p}':float(np.percentile(times,p)) if times else None for p in [50,95]}
        summary.append(record)
    tts=optional(raw/'voxcpm2.json');content=optional(raw/'tts-content.json')
    initial=optional(raw/'tts.json');retry=optional(raw/'tts-retry.json')
    cost=optional(raw/'cost.json');pipeline=optional(raw/'real-pipeline.json');deployment=optional(raw/'deployment.json')
    samples=manifest.get('samples',[]) if manifest else []
    sanitized={'asr':summary,'samples':[{k:x[k] for k in ['id','source','split','dialect','duration','sha256']} for x in samples],
               'tts':[{k:v for k,v in x.items() if k!='path'} for x in tts or []],
               'tts_content':content,'real_pipeline':pipeline,'gateway_deployment':deployment,
               'budget':{k:cost[k] for k in ['cap','committed','actual','unknown']} if cost else None,
               'openrouter_speech_attempts':len(cost['calls']) if cost else None,
               'availability':{name:optional(raw/(name+'.json')) is not None for name in ['asr','voxcpm2','tts-content','tts','tts-retry','real-pipeline','cost','deployment']}}
    (out/'evaluation-results.json').write_text(json.dumps(sanitized,ensure_ascii=False,indent=2))
    lines=['# ASR/TTS PoC 测试报告','','执行日期：2026-10-12。Intel macOS / Python 3.12；API结果不代表本机GPU部署。','','## ASR真实测试','']
    if manifest:
        dialects='/'.join(f'{k}{v}' for k,v in sorted(Counter(x['dialect'] for x in samples).items()))
        words=sum(len(normalize(x.get('reference','')).split()) for x in samples)
        lines += [f"SADA test划分固定{len(samples)}条（{sum(x['duration'] for x in samples):.2f}秒、{words}个归一化参考词），{len({x['source'] for x in samples})}个源录音；{dialects}。"]
    else:lines += ['样本manifest缺失：未取得样本统计。']
    lines += [f"当前ASR结果：成功{sum(x['successful'] for x in summary)}次 / 请求{sum(x['attempted'] for x in summary)}次；失败{sum(x['failed'] for x in summary)}次。" if rows is not None else 'ASR：未执行，未取得结果。','',
              '| 模型 | 条件 | 成功/请求 | micro WER | CER | API响应P50/P95秒 |','|---|---|---:|---:|---:|---:|']
    for x in summary:lines.append(f"| {x['model']} | {x['condition']} | {x['successful']}/{x['attempted']} | {percent(x['wer']['rate'])} | {percent(x['cer']['rate'])} | {seconds(x['latency_seconds']['p50'])}/{seconds(x['latency_seconds']['p95'])} |")
    valid=[x for x in summary if x['condition']=='clean' and x['wer']['rate'] is not None]
    if valid:lines += ['',f"原音频中，本次取得结果的最低WER为 {min(valid,key=lambda x:x['wer']['rate'])['model']}。这是有限样本的描述，不是生产排名。"]
    lines += ['','样本集中于少量方言/节目/说话人；未挑除错误样本、未微调。PCMU变体是人工编码劣化，不是Genesys录音。归一化保留数字英文；严格WER及S/D/I可从本地原始结果复算。','','## TTS真实测试','']
    if tts is None:lines += ['VoxCPM2：未执行，未取得合成结果。']
    else:
        good=[x for x in tts if x.get('status')=='success']
        lines += [f'VoxCPM2官方Nano-vLLM演示成功{len(good)}/{len(tts)}条原创文本。源码revision见公开JSON，后端权重revision未公开；零参考音频Voice Design，没有克隆SADA说话人。']
        if good:lines += [f"全响应耗时{min(x['elapsed_seconds'] for x in good):.2f}–{max(x['elapsed_seconds'] for x in good):.2f}秒，生成音频{min(x['duration'] for x in good):.2f}–{max(x['duration'] for x in good):.2f}秒。不是TTFA或私有GPU吞吐。"]
    for label,items in [('初次WAV请求',initial),('MP3重试',retry)]:
        if items is None:lines += [f'OpenRouter {label}：未执行。'];continue
        models=sorted({x['model'] for x in items})
        for model in models:
            group=[x for x in items if x['model']==model]
            lines += [f"OpenRouter {label} / {model}：成功{sum(x.get('status')==200 and bool(x.get('path')) for x in group)}/{len(group)}，HTTP状态{dict(Counter(str(x.get('status','exception')) for x in group))}。"]
    lines += ['','| 模型/案例 | 合成回读WER | 判断 |','|---|---:|---|']
    for x in content or []:
        wer=x.get('scores',{}).get('wer',{}).get('error_rate')
        note='内容代理指标，不等于母语MOS'
        if wer is None:note='未取得回读，不计通过'
        elif x['case']=='ar_digits' and wer>0:note='裸数字存在回读错误；关键ID需逐位朗读和专门验收'
        lines.append(f"| {x['model']} / {x['case']} | {percent(wer)} | {note} |")
    if content is None:lines += ['','TTS回读：未执行。']
    lines += ['','回读使用ASR作为内容代理，ASR自身可能出错；不能代替母语听评。类型化ID逐位朗读已实现，并在分句阶段保持原子片段；日期、金额和专名需要业务发音词典。单个成功案例不能证明所有数字已解决。','','## 真实集成串联与控制测试','']
    if pipeline is None:lines += ['真实串联：未执行。']
    else:
        lines += [f"Silero VAD→Qwen ASR→业务契约替身→官方VoxCPM2，快速注入{len(pipeline)}条；串联完成{sum(bool(x['pipeline_completed']) for x in pipeline)}条，自动VAD产生回合{sum(x['vad_utterances']>0 for x in pipeline)}条，显式发送回退{sum(bool(x.get('manual_submit_fallback')) for x in pipeline)}条。未经过真实麦克风或Genesys。",'',
                  '| 样本 | VAD回合 | 显式发送回退 | 输出帧 | 串联完成 |','|---|---:|---|---:|---|']
        for x in pipeline:lines.append(f"| {x['id']} | {x['vad_utterances']} | {x.get('manual_submit_fallback',False)} | {x['output_frames']} | {x['pipeline_completed']} |")
    lines += ['','串联完成只指音频返回，业务为替身；不报告真实业务准确率、转人工召回或MOS。VAD遗漏保留为限制，显式发送不算自动VAD成功。', '',
              '单元、协议、失败路径与客户端重连测试的实际命令、数量和独立复核见 [Review记录](review.md)。CUDA模型加载和吞吐尚未实测。三个diagram-design HTML已自检和浏览器预览。','','## 费用、来源与数据保护','']
    if deployment:
        lines += [f"CPU Gateway镜像 {deployment['image']}，Compose配置退出码{deployment['compose_validation_exit']}，健康{deployment['health']['status']}，网站{deployment['website_served']}；WebSocket准入检查{deployment['websocket_admission']}，断线后会话{deployment['after_disconnect_metrics']['sessions']}。该检查未调用模型，不代表GPU/业务/500路生产压测。"]
    else:lines += ['CPU Gateway：未执行部署检查，未取得结果。']
    if cost:lines += [f"授权累计上限 ${cost['cap']:.2f}。接口回传费用 ${cost['actual']:.6f}；{cost['unknown']}次费用未知/预留，记账占用 ${cost['committed']:.6f}。未读账户/余额；预留不是已核对账单。付费请求前持久化唯一call_id，异常仍占用预算；全部批次复用同一台账。"]
    else:lines += ['费用台账缺失：未取得费用信息，不能宣称预算通过。']
    lines += ['','凭据只隐藏输入并发到OpenRouter，不写入代码、结果、报告或GitHub。SADA音频/转录保存在忽略路径；公开JSON只有样本ID、hash、聚合指标和原创TTS文本。SADA CC BY-NC-SA4.0仅作非商业研究测试。','','## 当前验收结论','',
              '本报告记录已执行部分与失败，未执行不计通过。当前小样本WER、响应时延、关键数字与VAD反例不能支持生产质量达标。下一阶段须做授权业务盲测、母语听评、Genesys实联、目标CUDA加载和3000calls/h/500路真实回合压测；模拟结果不能替代。']
    (out/'test-report.md').write_text('\n'.join(lines)+'\n')
    return sanitized


def main():
    p=argparse.ArgumentParser();p.add_argument('--raw',default='artifacts/raw');p.add_argument('--out',default='docs');p.add_argument('--manifest',default='data/sada/manifest.json');a=p.parse_args()
    result=generate(a.raw,a.out,a.manifest)
    print('report generated; successful ASR:',sum(x['successful'] for x in result['asr']))

if __name__=='__main__':main()
