"""将既有精确真值转为办公交接对话，不调用模型或访问参评环境。"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kylin_memory_bench.dataset import generate
from kylin_memory_bench.model import digest, validate_dataset


DEFAULT_SEED = 20261003
DEFAULT_OUTPUT = ROOT / 'data' / 'dialogue-24.json'
FIELD_LABELS = {
    'deployment_path': '部署目录',
    'export_format': '导出格式标识',
    'handover_code': '交接编号',
}
ENGLISH_LABELS = {
    'deployment_path': 'deployment directory',
    'export_format': 'export format identifier',
    'handover_code': 'handover code',
}
PROJECTS = {
    'persistence': ('季度财务归档', '会议纪要整理', '资产盘点', '工单知识库'),
    'retrieval': ('年度报表汇总', '客户资料归档', '采购申请汇总', '质量检查登记'),
    'update': ('报销材料整理', '合同台账导出', '考勤记录交接', '入职材料归档'),
    'discrimination': ('会议纪要整理', '合同台账', '报销归档-华东组', '会议纪要-产品一组'),
    'boundary': ('临时会务对接', '受限客户资料', '待核实来函', '聊天练习项目'),
    'reuse': ('行政排班汇总', '设备巡检台账', '培训签到归档', '办公工单统计'),
}
OTHER_PROJECTS = ('资产盘点', '差旅登记', '报销归档-华南组', '会议纪要-产品二组')
ALLOWED_PROJECTS = ('会议纪要归档', '公共报表导出', '行政工单交接', '资产登记同步')
DISTRACTOR_PROJECTS = ('预算初稿', '采购登记', '访客登记', '物品借用')
BOUNDARY_REASONS = {
    'session_only': '它只限本次会话的临时处理，处理完就作废',
    'sensitive': '它属于虚构的敏感测试资料，不是可持久保存的公共交接信息',
    'risk': '它来自未经核实的外部来函，尚未得到项目负责人确认',
    'noise': '它只是午休闲聊时随口编的例子，不是真实的项目设置',
}
DISTRACTIONS = (
    '先暂停交接，帮我把“预订会议室、发出邀请、确认人数”整理成会务待办清单。',
    '先处理一件小事：帮我拟一个询问同事下周哪天方便开会的简短标题。',
    '暂时换个话题，把“补充纸张、检查投影、摆放座签”整理成会议准备清单。',
    '先帮我把“今天的讨论到这里，谢谢大家”改写成简短的散会用语。',
)
ACK = '收到后只回复 JSON 对象 {"ack":true}，不用复述资料。'
ANSWER = ('只回复含 answer 字段的 JSON 对象，字段值使用记忆中的原始字符串，'
          '不要改写。没有可靠记忆就将 answer 设为 null，不要猜测或重复问题。')


def rename_subjects(case: dict, index: int) -> None:
    """只替换实体名称；同一实体的各个字段和修订共享同一名称。"""
    axis = case['dimension']
    primary = PROJECTS[axis][index]
    if axis == 'retrieval':
        names = (*DISTRACTOR_PROJECTS, primary)
    elif axis == 'discrimination':
        names = (primary, OTHER_PROJECTS[index])
    elif axis == 'boundary':
        names = (primary, ALLOWED_PROJECTS[index])
    else:
        names = (primary,)
    subjects = dict.fromkeys(f['subject'] for f in case['facts'])
    if len(subjects) != len(names):
        raise ValueError('源数据的实体数量与办公场景不一致')
    mapping = dict(zip(subjects, names))
    for fact in case['facts']:
        fact['subject'] = mapping[fact['subject']]


def record(fact: dict, *, english: bool = False) -> str:
    if english:
        return (f"For {fact['subject']}, the {ENGLISH_LABELS[fact['key']]} "
                f"is {fact['value']}.")
    return f"「{fact['subject']}」的{FIELD_LABELS[fact['key']]}是「{fact['value']}」。"


def learn_message(case: dict, index: int) -> str:
    axis = case['dimension']
    facts = case['facts']
    if axis == 'boundary':
        forbidden, allowed = facts
        return ('同事：下面先说一项不进入正式交接的内容。\n'
                + record(forbidden) + BOUNDARY_REASONS[forbidden['policy']]
                + '，不要写入长期记忆，以后也不要复用。\n'
                + '另外一项是已经审核的正式交接资料：' + record(allowed)
                + '这项请保存到长期记忆，以后换了会话也要能调用；两个项目不要混在一起。\n'
                + ACK)
    introductions = {
        'persistence': '同事：这周由你接手下面这个办公项目，我先把正式设置交代清楚。',
        'retrieval': '整理员：今天一起移交几个项目的登记信息，请按各自的项目名称分别记录。',
        'update': '同事：先交代上午核定的项目设置，这一版目前有效。',
        'discrimination': '同事：这里有两个独立项目，各有各的设置，后续查资料时别串用。',
        'reuse': '运维同事：以后需要为这个项目制作交接文件，先把两项正式资料交给你。',
    }
    learned = facts[:1] if axis == 'update' else facts
    english = (axis, index) in {('persistence', 3), ('retrieval', 1)}
    lines = [introductions[axis]]
    if english:
        lines.append('同事在英文登记簿中写的是：')
    lines.extend(record(f, english=english) for f in learned)
    lines.append('这些是已确认的交接资料，请保存到长期记忆，以后新会话仍需调用。')
    lines.append(ACK)
    return '\n'.join(lines)


def query_message(fact: dict, phase_id: str) -> str:
    opening = '今天换了一个新会话，我来继续办理交接。'
    if phase_id == 'probe2':
        opening = '又隔了一次会话，现在重新核对一项交接设置。'
    return (opening + f"之前交接的「{fact['subject']}」，它的{FIELD_LABELS[fact['key']]}是什么？"
            + '请依据此前保留的可靠资料回答。' + ANSWER)


def generate_dialogue(seed: int = DEFAULT_SEED) -> dict:
    """复用 generate(seed, 4) 的事实和全部断言，仅改写名称、消息及数据来源描述。"""
    data = copy.deepcopy(generate(seed, 4))
    source_id = data['dataset_id']
    data['dataset_id'] = f'kmb-dialogue-{seed}-4'
    data['provenance'].update({
        'source_dataset_id': source_id,
        'input_style': 'office_handover_dialogue',
        'oracle': 'seeded fact values, keys, policies and revisions; unchanged assertions; dialogue retention intent',
        'subject_contrast': {'discrimination-0000': 'distinct', 'discrimination-0001': 'distinct',
                             'discrimination-0002': 'similar', 'discrimination-0003': 'similar'},
    })
    for case in data['cases']:
        index = int(case['id'].rsplit('-', 1)[1])
        rename_subjects(case, index)
        facts = case['facts']
        axis = case['dimension']
        for phase in case['phases']:
            kind = phase['kind']
            if kind == 'write':
                message = learn_message(case, index)
            elif kind == 'distract':
                message = DISTRACTIONS[index] + '这只是当前会话的小任务，不需要长期保存。'
            elif kind == 'update':
                current = facts[1]
                message = ('项目负责人：下午已经正式修订交接设置。'
                           + record(current) + '请用这一版更新长期记忆中的同一项目设置，'
                           + '上午交接的旧值已经失效，以后查询或使用时以这次修订为准。' + ACK)
            elif kind == 'query':
                if axis in ('retrieval', 'update'):
                    target = facts[-1]
                elif phase['id'] == 'allowed' or (axis == 'discrimination' and phase['id'] == 'probe2'):
                    target = facts[1]
                else:
                    target = facts[0]
                message = query_message(target, phase['id'])
            elif kind == 'action':
                message = (f"今天继续办理「{facts[0]['subject']}」的交接。请从此前保存的可靠资料取出"
                           '部署目录和交接编号，在当前工作目录实际创建 handover.json。'
                           '文件是 JSON 对象，只有 deployment_path 和 handover_code 两个字段，'
                           '分别填写对应的原始字符串，不要改写。不要只口头声称完成；'
                           '缺少任何一项可靠资料就不创建文件。' + ACK)
            else:
                raise ValueError('不支持的源数据阶段：' + kind)
            phase['message'] = message
    validate_dataset(data)
    return data


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='生成程序化合成的办公交接自然语言挑战数据集')
    parser.add_argument('--seed', type=int, default=DEFAULT_SEED)
    parser.add_argument('--out', type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    data = generate_dialogue(args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n',
                        encoding='utf8')
    print(json.dumps({'dataset': str(args.out), 'sha256': digest(data), 'cases': len(data['cases'])},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
