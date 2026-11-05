"""Real Docker smoke test. Uses disposable volumes, ports and ignored test keys."""

import json
import os
import secrets
import select
import shutil
import socket
import ssl
import subprocess
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
IMAGE = "eclipse-mosquitto:2.0"


def run(*args, check=True, env=None):
    return subprocess.run(args, capture_output=True, text=True, check=check,
                          timeout=90, env=env)


class LocalInfrastructureTest(unittest.TestCase):
    def test_local_infrastructure(self):
        # Parent directory protects test keys; only this disposable project is removed.
        ignored = ROOT / "tests/integration/secrets"
        ignored.mkdir(exist_ok=True)
        self.assertEqual(run("git", "-C", str(ROOT), "check-ignore", str(ignored)).returncode, 0)
        with tempfile.TemporaryDirectory(prefix="smoke-", dir=ignored) as directory:
            self.certs = Path(directory) / "certs"
            self.certs.mkdir(mode=0o700)
            self.broker_certs = Path(directory) / "broker"
            self.provision()
            self.project = "issue16-" + secrets.token_hex(4)
            env = {key: value for key, value in os.environ.items()
                   if not key.startswith(("POSTGRES_", "COMPOSE_", "MQTT_CERT_DIR"))}
            env.update({"POSTGRES_USER": "smoke", "POSTGRES_DB": "smoke",
                        "POSTGRES_PASSWORD": secrets.token_hex(24), "MQTT_CERT_DIR": str(self.broker_certs)})
            self.env = env
            base = ["docker", "compose", "--env-file", "/dev/null", "-p", self.project,
                    "-f", str(ROOT / "deploy/compose.yaml"), "--profile", "tls",
                    "--profile", "dev-insecure"]
            config = json.loads(run(*base, "config", "--format", "json", env=env).stdout)
            for service in config["services"].values():
                for port in service.get("ports", []):
                    self.assertEqual(port["host_ip"], "127.0.0.1")
                    port["published"] = "0"
            self.assertNotEqual(config["services"]["mqtt-dev"]["networks"],
                                config["services"]["mqtt-tls"]["networks"])
            print("PASS: Compose profiles, loopback-only bindings and dev network isolation", flush=True)
            for name in ("POSTGRES_USER", "POSTGRES_DB", "POSTGRES_PASSWORD"):
                invalid = dict(env, **{name: ""})
                self.assertNotEqual(run(*base, "config", "-q", env=invalid, check=False).returncode, 0)
            print("PASS: missing/empty PostgreSQL environment rejected", flush=True)
            # Resolve the actual Compose file, changing only published ports for isolation.
            resolved = Path(directory) / "compose.json"
            resolved.write_text(json.dumps(config))
            resolved.chmod(0o600)
            self.compose = ["docker", "compose", "-p", self.project, "-f", str(resolved),
                            "--profile", "tls", "--profile", "dev-insecure"]
            try:
                run(*self.compose, "up", "-d", "--build", "--wait", "--wait-timeout", "60", env=env)
                self.broker_permissions()
                self.client_key_visibility()
                self.database()
                self.reachability()
                self.tls_handshakes()
                self.authorization()
            finally:
                logs = run(*self.compose, "logs", "--no-color", "mqtt-tls", "mqtt-dev", check=False, env=env)
                print("BROKER LOG BEGIN\n" + logs.stdout + logs.stderr + "BROKER LOG END", flush=True)
                run(*self.compose, "down", "-v", "--rmi", "local", "--remove-orphans", env=env)

    def broker_permissions(self):
        self.assertEqual(run(*self.compose, "exec", "-T", "mqtt-tls", "id", "-u", env=self.env).stdout.strip(), "1883")
        acl = run(*self.compose, "exec", "-T", "mqtt-tls", "stat", "-c", "%u:%g %a",
                  "/mosquitto/config/acl", env=self.env).stdout.strip()
        self.assertEqual(acl, "1883:1883 600")
        files = run(*self.compose, "exec", "-T", "mqtt-tls", "ls", "-1", "/mosquitto/certs", env=self.env).stdout.split()
        self.assertEqual(sorted(files), ["ca.crt", "server.crt", "server.key"])
        logs = run(*self.compose, "logs", "mqtt-tls", "mqtt-dev", env=self.env).stdout.lower()
        for warning in ("warning:", "chown:", "read-only file system"):
            self.assertNotIn(warning, logs)
        print("PASS: broker uid1883, ACL owner1883:1883 mode0600, server-only key mount; no ownership/startup warnings", flush=True)

    def client_key_visibility(self):
        for identity in (None, "gw-a", "gw-b", "backend", "unknown", "wrong"):
            command = self.client(identity, "mosquitto_pub")
            prefix = command[:command.index(IMAGE) + 1]
            files = run(*prefix, "find", "/certs", "-type", "f").stdout.split()
            expected = ["/certs/ca.crt"] + ([] if identity is None else [
                f"/certs/{identity}.crt", f"/certs/{identity}.key"])
            self.assertEqual(sorted(files), sorted(expected))
        print("PASS: each client sees only public CA and its own certificate/key; anonymous sees CA only", flush=True)

    def provision(self):
        def openssl(*args):
            run("openssl", *args)

        ca = self.certs.parent
        openssl("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                "-subj", "/CN=issue16-test-ca", "-keyout", str(ca / "ca.key"),
                "-out", str(self.certs / "ca.crt"))
        for name in ("server", "gw-a", "gw-b", "backend", "unknown"):
            openssl("req", "-new", "-newkey", "rsa:2048", "-nodes", "-subj", f"/CN={name}",
                    "-keyout", str(self.certs / f"{name}.key"), "-out", str(ca / f"{name}.csr"))
            extension = ca / "extension.cnf"
            extension.write_text("basicConstraints=CA:FALSE\n" + (
                "extendedKeyUsage=serverAuth\nsubjectAltName=DNS:mqtt-tls,DNS:localhost,IP:127.0.0.1\n"
                if name == "server" else "extendedKeyUsage=clientAuth\n"))
            openssl("x509", "-req", "-in", str(ca / f"{name}.csr"), "-CA", str(self.certs / "ca.crt"),
                    "-CAkey", str(ca / "ca.key"), "-CAcreateserial", "-days", "1",
                    "-extfile", str(extension), "-out", str(self.certs / f"{name}.crt"))
        # Wrong certificate has the expected CN, but is not signed by the trusted CA.
        openssl("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1", "-subj", "/CN=gw-a",
                "-keyout", str(self.certs / "wrong.key"), "-out", str(self.certs / "wrong.crt"))
        for path in self.certs.iterdir():
            path.chmod(0o600)
        self.broker_certs.mkdir(mode=0o750)
        for name in ("ca.crt", "server.crt", "server.key"):
            shutil.copyfile(self.certs / name, self.broker_certs / name)
            (self.broker_certs / name).chmod(0o640)
        # Change only this disposable mount's group; host user retains ownership for cleanup.
        run("docker", "run", "--rm", "--user", "0:0", "--entrypoint", "chgrp",
            "--mount", f"type=bind,src={self.broker_certs},dst=/broker", IMAGE, "-R", "1883", "/broker")

    def database(self):
        def sql(statement):
            return run(*self.compose, "exec", "-T", "postgres", "psql", "-U", "smoke", "-d", "smoke",
                       "-v", "ON_ERROR_STOP=1", "-Atc", statement, env=self.env).stdout.strip()

        container = run(*self.compose, "ps", "-q", "postgres", env=self.env).stdout.strip()
        self.assertEqual(run("docker", "inspect", "-f", "{{.State.Health.Status}}", container).stdout.strip(), "healthy")
        sql("CREATE TABLE smoke_persistence (value integer); INSERT INTO smoke_persistence VALUES (16)")
        run(*self.compose, "up", "-d", "--force-recreate", "--wait", "--wait-timeout", "60", "postgres", env=self.env)
        self.assertEqual(sql("SELECT value FROM smoke_persistence"), "16")
        print("PASS: PostgreSQL healthcheck and persistence after container recreation", flush=True)

    def reachability(self):
        interfaces = json.loads(run("ip", "-j", "-4", "address", "show", "up").stdout)
        addresses = [entry["local"] for interface in interfaces
                     if "LOOPBACK" not in interface["flags"]
                     and not interface["ifname"].startswith(("docker", "br-", "veth"))
                     for entry in interface["addr_info"] if entry.get("scope") == "global"]
        self.assertTrue(addresses, "Non-loopback host IPv4 required, reachability NOT_VERIFIED")
        ports = []
        for service, target in (("postgres", "5432"), ("mqtt-dev", "1883"), ("mqtt-tls", "8883")):
            port = int(run(*self.compose, "port", service, target, env=self.env).stdout.strip().rsplit(":", 1)[1])
            with socket.create_connection(("127.0.0.1", port), timeout=3):
                pass
            ports.append((service, port))
        for address in addresses:
            def probe(port):
                return run("docker", "run", "--rm", "--user", "1000:1000", "--network", "bridge",
                           IMAGE, "nc", "-n", "-z", "-w", "2", address, str(port), check=False)

            with socket.socket() as control:
                control.bind((address, 0))
                control.listen()
                result = probe(control.getsockname()[1])
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                print(f"PASS: separate-network client reaches non-loopback control listener on {address}", flush=True)
                for service, port in ports:
                    result = probe(port)
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    print(f"PASS: {service} reachable via localhost, rejected via non-loopback {address}:{port}", flush=True)

    def tls_handshakes(self):
        port = int(run(*self.compose, "port", "mqtt-tls", "8883", env=self.env).stdout.strip().rsplit(":", 1)[1])
        context = ssl.create_default_context(cafile=str(self.certs / "ca.crt"))
        context.load_cert_chain(self.certs / "gw-a.crt", self.certs / "gw-a.key")
        with socket.create_connection(("127.0.0.1", port), timeout=3) as raw:
            with context.wrap_socket(raw, server_hostname="localhost") as secured:
                self.assertIn(secured.version(), ("TLSv1.2", "TLSv1.3"))
        print("PASS: published TLS port verifies server CA and hostname", flush=True)

    def client(self, identity, tool, *args):
        # A terminal keeps Mosquitto's SUBACK debug output line-buffered.
        files = ["ca.crt"] + ([] if identity is None else [f"{identity}.crt", f"{identity}.key"])
        mounts = [arg for name in files for arg in (
            "--mount", f"type=bind,src={self.certs / name},dst=/certs/{name},readonly")]
        return ["docker", "run", "--rm", "--tty", "--user", f"{os.getuid()}:{os.getgid()}",
                "--network", self.project + "_local", *mounts, IMAGE,
                tool, "-h", "mqtt-tls", "-p", "8883", "-V", "mqttv5", "-q", "1",
                "--cafile", "/certs/ca.crt", *([] if identity is None else [
                    "--cert", f"/certs/{identity}.crt", "--key", f"/certs/{identity}.key"]), *args]

    def publish(self, identity, topic, allowed=True, *extra):
        result = run(*self.client(identity, "mosquitto_pub", "-d", "-t", topic,
                                  "-m", "issue16-smoke", *extra), check=False)
        output = result.stdout + result.stderr
        if allowed:
            self.assertEqual(result.returncode, 0, output)
            self.assertRegex(output, r"received PUBACK \(Mid: 1, RC:(?:0|16)\)")
        else:
            self.assertIn("RC:135", output, "Expected MQTT5 PUBACK Not authorized")

    def exchange(self, reader, writer, topic, allowed=True, subscription=None):
        name = self.project + "-sub-" + secrets.token_hex(4)
        command = self.client(reader, "mosquitto_sub", "-d", "-t", subscription or topic,
                              "-C", "1", "-W", "45")
        command[2:2] = ["--name", name]
        started = time.monotonic()
        subscriber = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        initial = b""
        deadline = time.monotonic() + 10
        try:
            while b"Subscribed (mid: 1):" not in initial and time.monotonic() < deadline:
                if select.select([subscriber.stdout], [], [], 0.2)[0]:
                    chunk = os.read(subscriber.stdout.fileno(), 4096)
                    if not chunk:
                        break
                    initial += chunk
            self.assertIn(b"received SUBACK", initial, initial.decode())
            if allowed:
                self.assertIn(b"Subscribed (mid: 1): 1", initial, initial.decode())
            self.publish(writer, topic)
            if not allowed:
                # Reserve at least 8 seconds after publishing, even with slow Docker startup.
                self.assertLess(time.monotonic() - started, 37,
                                "Docker publisher consumed the negative receive window; NOT_VERIFIED")
            try:
                # MQTT's receive timer and Docker's process completion are separate deadlines.
                tail, _ = subscriber.communicate(timeout=60)
            except subprocess.TimeoutExpired as error:
                output = (initial + (error.output or b"")).decode(errors="replace")
                self.fail(f"Docker subscriber process timeout after 60s for {reader} on {subscription or topic}; "
                          f"MQTT authorization result NOT_VERIFIED\n{output}")
            output = (initial + tail).decode()
            if allowed:
                self.assertEqual(subscriber.returncode, 0, output)
                self.assertIn("issue16-smoke", output)
            else:
                # Mosquitto may grant a subscription while filtering unauthorized delivery.
                self.assertEqual(subscriber.returncode, 27, output)
                self.assertNotIn("issue16-smoke", output)
        finally:
            try:
                if subscriber.poll() is None:
                    subscriber.kill()
                subscriber.communicate(timeout=10)
            finally:
                subscriber.stdout.close()
                removed = subprocess.run(["docker", "rm", "-f", name], capture_output=True,
                                         text=True, timeout=10)
                self.assertTrue(removed.returncode == 0 or "No such container" in removed.stderr,
                                f"Subscriber container cleanup failed: {removed.stderr}")
        if not allowed:
            print(f"PASS: denied receive {reader} on {subscription or topic}: "
                  f"MQTT exit27, no payload; Docker process completed in {time.monotonic() - started:.2f}s",
                  flush=True)

    def authorization(self):
        for identity in (None, "wrong"):
            result = run(*self.client(identity, "mosquitto_pub", "-t", "iot/v1/gw/gw-a/uplink/status",
                                      "-m", "smoke"), check=False)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            print(f"PASS: {'anonymous/no certificate' if identity is None else 'untrusted certificate'} rejected by TLS", flush=True)
        auth_logs = run(*self.compose, "logs", "mqtt-tls", env=self.env).stdout
        self.assertIn("peer did not return a certificate", auth_logs)
        self.assertIn("certificate verify failed", auth_logs)
        for gateway in ("gw-a", "gw-b"):
            for suffix in ("telemetry", "alert", "status", "schedule-ack", "command-ack"):
                self.exchange("backend", gateway, f"iot/v1/gw/{gateway}/uplink/{suffix}")
            for suffix in ("schedule", "command"):
                self.exchange(gateway, "backend", f"iot/v1/gw/{gateway}/downlink/{suffix}")
        print("PASS: both Gateways and Backend exchange every allowlisted topic at MQTT5 QoS1", flush=True)
        self.publish("gw-a", "iot/v1/gw/gw-b/uplink/telemetry", False,
                     "-i", "gw-b", "-u", "backend")
        self.publish("gw-b", "iot/v1/gw/gw-a/uplink/telemetry", False)
        self.publish("gw-a", "iot/v1/gw/gw-a/downlink/command", False)
        self.publish("backend", "iot/v1/gw/gw-a/uplink/telemetry", False)
        self.publish("unknown", "iot/v1/gw/unknown/uplink/status", False)
        self.publish("gw-a", "iot/v1/gw/gw-a/uplink/unlisted", False)
        print("PASS: cross-Gateway writes, ClientID/username spoof, reversed roles, unknown CN and unlisted topic denied with PUBACK 135", flush=True)
        self.exchange("gw-a", "backend", "iot/v1/gw/gw-b/downlink/command", False)
        self.exchange("gw-b", "backend", "iot/v1/gw/gw-a/downlink/command", False)
        self.exchange("gw-a", "gw-b", "iot/v1/gw/gw-b/uplink/telemetry", False, "iot/v1/gw/#")
        self.exchange("backend", "backend", "iot/v1/gw/gw-a/downlink/command", False)
        print("PASS: cross-Gateway reads, wildcard leakage and Backend downlink reads deliver no messages", flush=True)


if __name__ == "__main__":
    unittest.main()
