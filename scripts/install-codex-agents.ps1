param([string]$CodexDirectory = (Join-Path $env:USERPROFILE '.codex'))

$ErrorActionPreference = 'Stop'
$agentProjectRoot = Split-Path $PSScriptRoot -Parent
. (Join-Path $PSScriptRoot 'env.ps1')
$agentInstaller = @'
import hashlib,json,sys,tomllib
from datetime import datetime,timezone
from pathlib import Path
root=Path(sys.argv[1]).resolve()
target=Path(sys.argv[2]).resolve()
source=root/'.codex/agents'
config_path=target/'config.toml'
original=config_path.read_bytes() if config_path.exists() else b''
config=tomllib.loads(original.decode('utf-8-sig'))
defaults=tomllib.loads((root/'.codex/config.toml').read_text(encoding='utf-8-sig'))['agents']
existing=config.get('agents')
if existing is not None and any(existing.get(k)!=v for k,v in defaults.items()):
    raise SystemExit('Existing personal [agents] defaults differ; refusing a silent overwrite. Project defaults and explicit spawn remain usable.')
profiles=[]
for path in sorted(source.glob('task_*.toml')):
    data=path.read_bytes();value=tomllib.loads(data.decode('utf-8'))
    assert all(isinstance(value.get(k),str) and value[k] for k in ('name','description','developer_instructions','model','model_reasoning_effort'))
    assert value['name']==path.stem
    destination=target/'agents'/path.name
    if destination.exists() and destination.read_bytes()!=data:
        raise SystemExit('Existing named personal profile differs; refusing silent overwrite: '+path.name)
    profiles.append((path,data,destination))
stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
policy=(root/'.codex/agent-routing.instructions.md').read_text(encoding='utf-8')
guide=target/'AGENTS.md'
prior_guide=guide.read_text(encoding='utf-8-sig') if guide.exists() else ''
marker='## Persistent subagent model routing'
if marker in prior_guide and policy.strip() not in prior_guide:
    raise SystemExit('Existing routing instructions differ; refusing silent overwrite.')
backup=None
if existing is None:
    backup=target/'backups'/('config-before-agent-routing-'+stamp+'.toml')
    backup.parent.mkdir(parents=True,exist_ok=True)
    backup.write_bytes(original)
    suffix='\n\n'+(root/'.codex/config.toml').read_text(encoding='utf-8-sig')
    updated=original.decode('utf-8-sig')+suffix
    resolved=tomllib.loads(updated)
    assert {k:v for k,v in resolved.items() if k!='agents'}==config
    config_path.write_text(updated,encoding='utf-8',newline='\n')
for path,data,destination in profiles:
    destination.parent.mkdir(parents=True,exist_ok=True)
    if not destination.exists():
        destination.write_bytes(data)
if marker not in prior_guide:
    if guide.exists():
        policy_backup=target/'backups'/('AGENTS-before-agent-routing-'+stamp+'.md')
        policy_backup.parent.mkdir(parents=True,exist_ok=True)
        policy_backup.write_bytes(guide.read_bytes())
    guide.write_text(prior_guide.rstrip()+'\n\n'+policy,encoding='utf-8',newline='\n')
if backup is None:
    previous_backups=sorted((target/'backups').glob('config-before-agent-routing-*.toml'))
    backup=previous_backups[-1] if previous_backups else None
receipt={'personalDirectory':str(target),'backup':str(backup) if backup else None,'parentModelPreserved':True,'previousProfilesPreserved':True,'defaults':defaults,'profiles':[{'name':p.stem,'sha256':hashlib.sha256(d).hexdigest(),'path':str(dest)} for p,d,dest in profiles]}
out=root/'.cache/codex-agent-routing-installation.json'
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'installedProfiles':len(profiles),'parentModelPreserved':True,'defaults':defaults},ensure_ascii=False))
'@
$agentInstaller | & (Join-Path $agentProjectRoot '.venv/Scripts/python.exe') -B - $agentProjectRoot $CodexDirectory
if ($LASTEXITCODE -ne 0) { throw 'Codex agent installation did not complete; inspect its explanation.' }
