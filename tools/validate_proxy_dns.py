"""Exercise the actual proxy config across a Docker backend IP replacement.

Only uniquely named temporary containers/network are touched; no production
container, volume, credential or research data is used. Requires Docker.
"""

import argparse
import ipaddress
import json
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default="nginxinc/nginx-unprivileged:1.29-alpine")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    config = root / "web/nginx.conf"
    assert config.is_file()
    prefix = "xrt-dns-test-" + uuid.uuid4().hex[:12]
    names = [prefix + suffix for suffix in ("-a", "-b", "-block", "-proxy")]
    old, new, blocker, proxy = names

    def docker(*parts, check=True):
        return subprocess.run(["docker", *parts], check=check, text=True,
                              capture_output=True, timeout=90).stdout.strip()

    def address(name):
        return json.loads(docker("inspect", name))[0]["NetworkSettings"]["Networks"][prefix]["IPAddress"]

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    paths = ("/portal-api/releases?channel=BETA", "/portal-api/guide/public", "/api/v1/health")

    def wait_for(origin, hostname):
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            try:
                for path in paths:
                    with opener.open(origin + path, timeout=3) as response:
                        assert response.status == 200
                        assert response.read().decode().strip() == f"{hostname}|GET|{path}"
                request = urllib.request.Request(origin + "/api/v1/reports", data=b"{}", method="POST")
                with opener.open(request, timeout=3) as response:
                    assert response.read().decode().strip() == f"{hostname}|POST|/api/v1/reports"
                return
            except (urllib.error.URLError, TimeoutError, AssertionError):
                time.sleep(0.5)
        raise RuntimeError("Proxy did not follow the replacement backend within 40 seconds")

    # TemporaryDirectory only removes this newly created private test directory.
    with tempfile.TemporaryDirectory(prefix=prefix) as temporary:
        backend = Path(temporary) / "backend.conf"
        backend.write_text('server { listen 8000; listen 8001; location / { return 200 "$hostname|$request_method|$request_uri\\n"; } }\n', encoding="utf-8")
        try:
            network_ids = docker("network", "ls", "-q").splitlines()
            existing = json.loads(docker("network", "inspect", *network_ids))
            subnets = [ipaddress.ip_network(c["Subnet"]) for n in existing
                       for c in (n["IPAM"].get("Config") or []) if c.get("Subnet")]
            subnet = next(ipaddress.ip_network(f"10.254.{i}.0/24") for i in range(256)
                          if not any(ipaddress.ip_network(f"10.254.{i}.0/24").overlaps(s)
                                     for s in subnets if s.version == 4))
            docker("network", "create", "--subnet", str(subnet), prefix)

            def start_backend(name, hostname):
                docker("run", "-d", "--name", name, "--hostname", hostname,
                       "--network", prefix, "--network-alias", "portal", "--network-alias", "api",
                       "-v", str(backend.resolve()) + ":/etc/nginx/conf.d/default.conf:ro", args.image)

            start_backend(old, "before")
            old_ip = address(old)
            docker("run", "-d", "--name", proxy, "--network", prefix,
                   "--read-only", "--tmpfs", "/tmp", "--cap-drop", "ALL",
                   "--security-opt", "no-new-privileges:true", "-p", "127.0.0.1::8080",
                   "-v", str(config.resolve()) + ":/etc/nginx/conf.d/default.conf:ro", args.image)
            origin = "http://" + docker("port", proxy, "8080/tcp").splitlines()[0]
            wait_for(origin, "before")
            proxy_before = json.loads(docker("inspect", proxy))[0]
            docker("rm", "-f", old)
            # Occupy the previous address so the replacement must get a new IP.
            docker("run", "-d", "--name", blocker, "--network", prefix, "--ip", old_ip,
                   "--entrypoint", "sleep", args.image, "120")
            start_backend(new, "after")
            new_ip = address(new)
            assert new_ip != old_ip
            started = time.monotonic()
            wait_for(origin, "after")
            proxy_after = json.loads(docker("inspect", proxy))[0]
            assert proxy_before["State"]["StartedAt"] == proxy_after["State"]["StartedAt"]
            assert proxy_after["RestartCount"] == 0
            result = {"status": "PASS", "backend_ip_changed": True,
                      "proxy_restarted": False, "uri_query_and_post_preserved": True,
                      "recovery_seconds": round(time.monotonic() - started, 3)}
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
            print(json.dumps(result), flush=True)
        except Exception:
            subprocess.run(["docker", "logs", "--tail", "20", proxy], check=False)
            raise
        finally:
            for name in names:
                docker("rm", "-f", name, check=False)
            docker("network", "rm", prefix, check=False)


if __name__ == "__main__":
    main()
