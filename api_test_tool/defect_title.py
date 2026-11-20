"""Business attributes for UI defect titles, independent of test devices."""
import re

ENVIRONMENTS = ('dev', 'test', 'pre', 'prod', 'uat', 'staging', 'qa', 'local')
CLIENTS = ('B端', 'C端')
AI_TITLE_GUIDANCE = 'AI 整理 UI 缺陷时必须主动确定并填写 environment、client、module，标题统一为 【环境】【B端/C端】【功能/模块】 问题描述。environment 仅为 dev/test/pre/prod/uat/staging/qa/local；client 仅为 B端/C端，表示企业业务端或个人用户端；module 是实际功能模块。先复用用户明确指定的值，再依据测试目标地址、页面角色和业务上下文确认；同一范围批量复用已确认的环境与业务端，逐条确定模块。浏览器、操作系统、桌面/移动设备写入 test_environment（例如 macOS Chrome桌面），在缺陷描述的【测试环境】中自动展示；版本、视口及真机/模拟信息仅填写实际已知值，禁止写入 client；禁止用“同上”、地址或说明句替代属性。发布前读取保存结果并修正 title_attribute_gaps 中可由现有证据确定的值，再统一发布，不把已知属性留给用户逐条修改。确实无法判断时保留缺失值并集中说明一次，仍生成完整报告，不猜测、不阻止生成。'
PREFIX = re.compile(r'^【([^】]*)】\s*【([^】]*)】\s*【([^】]*)】\s*(.*)$', re.S)
LEGACY_PREFIX = re.compile(r'^\[([^\]]*)\]\s*【([^】]*)】\s*【([^】]*)】\s*(.*)$', re.S)


def attributes(environment='', client='', module=''):
    env = environment.strip().lower() if isinstance(environment, str) else ''
    side = client.strip() if isinstance(client, str) else ''
    feature = module.strip() if isinstance(module, str) else ''
    if (not feature or len(feature) > 60 or feature in {'同上', '无', '未标注模块', '待补充模块'}
            or re.search(r'[\[\]【】\r\n]', feature)):
        feature = ''
    return (env if env in ENVIRONMENTS else '', side if side in CLIENTS else '', feature)


def normalize_title(title, environment='', client='', module=''):
    match = PREFIX.fullmatch(title.strip()) or LEGACY_PREFIX.fullmatch(title.strip())
    if match:
        old_env, old_client, old_module, title = match.groups()
        environment, client, module = environment or old_env, client or old_client, module or old_module
    env, side, feature = attributes(environment, client, module)
    return f'【{env or "待补充环境"}】【{side or "待补充端"}】【{feature or "待补充模块"}】 {title.strip()}'


def validate_title(title):
    match = PREFIX.fullmatch(title.strip()) or LEGACY_PREFIX.fullmatch(title.strip())
    if not match or not all(attributes(*match.groups()[:3])) or not match[4].strip():
        raise ValueError('提交前请补齐标题：【环境】【B端/C端】【功能/模块】 问题描述；环境请选择 dev、test、pre、prod、uat、staging、qa 或 local')
