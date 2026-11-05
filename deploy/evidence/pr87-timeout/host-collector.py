"""Trusted one-off Host observer for the inspected PR87 test, outside the candidate."""
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
import unittest

root=Path('/tmp/lora-pr87-timeout-fix')
sys.path.insert(0,str(root/'tests/integration'))
import test_local_infra as infra
facts={}

def mount(source,target,read_only):
    source=Path(source)
    data={'source':str(source),'target':target,'read_only':read_only,
          'kind':'private_key' if source.suffix=='.key' else 'public_certificate'}
    if source.suffix=='.key':
        data['mode']=format(stat.S_IMODE(source.stat().st_mode),'04o')
    return data

original_keys=infra.LocalInfrastructureTest.client_key_visibility
def keys(self):
    original_keys(self)
    clients=[]
    for identity in (None,'gw-a','gw-b','backend','unknown','wrong'):
        command=self.client(identity,'mosquitto_pub')
        mounts=[]
        for i,arg in enumerate(command):
            if arg=='--mount':
                fields=command[i+1].split(',')
                values=dict(f.split('=',1) for f in fields if '=' in f)
                mounts.append(mount(values['src'],values['dst'],'readonly' in fields))
        clients.append({'identity':identity or 'anonymous','mounts':mounts})
    container=infra.run(*self.compose,'ps','-q','mqtt-tls',env=self.env).stdout.strip()
    mounts=json.loads(infra.run('docker','inspect','-f','{{json .Mounts}}',container).stdout)
    broker=[]
    for item in mounts:
        if item['Destination']=='/mosquitto/certs':
            names=infra.run(*self.compose,'exec','-T','mqtt-tls','ls','-1','/mosquitto/certs',env=self.env).stdout.split()
            for name in names:
                broker.append(mount(Path(item['Source'])/name,item['Destination']+'/'+name,not item['RW']))
    facts['SEC-KEY-MOUNT']={'runtime_inventory_complete':True,'clients':clients,'broker':{'mounts':broker}}
infra.LocalInfrastructureTest.client_key_visibility=keys

original_acl=infra.LocalInfrastructureTest.broker_permissions
def acl(self):
    original_acl(self)
    startup=infra.run(*self.compose,'logs','--no-color','mqtt-tls','mqtt-dev',env=self.env)
    print('ALL BROKER STARTUP LOG BEGIN\n'+startup.stdout+startup.stderr+'ALL BROKER STARTUP LOG END',flush=True)
    uid=int(infra.run(*self.compose,'exec','-T','mqtt-tls','id','-u',env=self.env).stdout)
    gid=int(infra.run(*self.compose,'exec','-T','mqtt-tls','id','-g',env=self.env).stdout)
    owner,group,mode=infra.run(*self.compose,'exec','-T','mqtt-tls','stat','-c','%u %g %a','/mosquitto/config/acl',env=self.env).stdout.split()
    images=[]
    for service in ('postgres','mqtt-tls','mqtt-dev'):
        container=infra.run(*self.compose,'ps','-q',service,env=self.env).stdout.strip()
        image=infra.run('docker','inspect','-f','{{.Image}}',container).stdout.strip()
        images.append({'service':service,'image':image})
    Path('/tmp/pr87-timeout-evidence/precommit-v2/runtime-images.json').write_text(json.dumps(images,indent=2)+'\n')
    facts['MQTT-ACL-PERM']={'runtime':True,'startup_logs_complete':True,'broker_uid':uid,'broker_gid':gid,
                          'acl_uid':int(owner),'acl_gid':int(group),'acl_mode':mode.zfill(4),'acl_readable':True}
infra.LocalInfrastructureTest.broker_permissions=acl

original_network=infra.LocalInfrastructureTest.reachability
def network(self):
    probes=[]
    original_run=infra.run
    def record(*args,**kwargs):
        result=original_run(*args,**kwargs)
        if args[:2]==('docker','run') and 'nc' in args:
            probes.append((args[-2],args[-1],result.returncode))
        return result
    infra.run=record
    try:
        original_network(self)
    finally:
        infra.run=original_run
    bindings=[]
    for service,target in (('postgres','5432'),('mqtt-dev','1883'),('mqtt-tls','8883')):
        address=original_run(*self.compose,'port',service,target,env=self.env).stdout.strip()
        ip,port=address.rsplit(':',1)
        matching=[p for p in probes if p[1]==port]
        assert matching and all(p[2]==1 for p in matching)
        bindings.append({'service':service,'host_ip':ip,'localhost_reachable':True,'non_loopback_reachable':False})
    facts['NET-LOOPBACK']={'runtime':True,'inventory_complete':True,'bindings':bindings,
        'network_context':'separate default Docker bridge -> Linux host non-loopback IPv4; excludes physical LAN/IPv6/WSL2',
        'representative':True,'non_loopback_address':probes[0][0],'control_reachable':probes[0][2]==0}
infra.LocalInfrastructureTest.reachability=network

original_auth=infra.LocalInfrastructureTest.authorization
def auth(self):
    original_auth(self)
    facts['TLS-AUTH/ACL-NEGATIVE']={key:True for key in ('runtime','server_verified','allowed_flow',
        'wrong_cert_rejected','anonymous_rejected','cross_gateway_publish_denied','cross_gateway_subscribe_denied')}
infra.LocalInfrastructureTest.authorization=auth

suite=unittest.defaultTestLoader.discover(str(root/'tests/integration'))
result=unittest.TextTestRunner(verbosity=2).run(suite)
Path('/tmp/pr87-timeout-evidence/precommit-v2/infra-observations.json').write_text(json.dumps(facts,indent=2)+'\n')
sys.exit(not result.wasSuccessful())
