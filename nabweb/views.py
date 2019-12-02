import abc
import asyncio
import json
import logging
import os
import re

from django.apps import apps
from django.views.generic import View
from django.shortcuts import render
from django.utils import translation
from django.conf import settings
from django.http import JsonResponse
from nabd.i18n import Config
from nabcommon.nabservice import NabService
from django.utils.translation import to_locale, to_language


class BaseView(View, metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def template_name(self):
        pass

    def get_locales(self):
        config = Config.load()
        return [
            (to_locale(lang), name, to_locale(lang) == config.locale)
            for (lang, name) in settings.LANGUAGES
        ]

    def get_context(self):
        user_locale = Config.load().locale
        user_language = to_language(user_locale)
        translation.activate(user_language)
        self.request.session[translation.LANGUAGE_SESSION_KEY] = user_language
        locales = self.get_locales()
        return {"current_locale": user_locale, "locales": locales}

    def get(self, request, *args, **kwargs):
        context = self.get_context()
        return render(request, self.template_name(), context=context)

class NabWebView(BaseView):
    def template_name(self):
        return "nabweb/index.html"

    def post(self, request, *args, **kwargs):
        config = Config.load()
        config.locale = request.POST["locale"]
        config.save()
        user_language = to_language(config.locale)
        translation.activate(user_language)
        self.request.session[translation.LANGUAGE_SESSION_KEY] = user_language
        locales = self.get_locales()
        return render(
            request,
            self.template_name(),
            context={"current_locale": config.locale, "locales": locales},
        )

class NabWebServicesView(BaseView):
    def template_name(self):
        return "nabweb/services/index.html"

    def get_context(self):
        context = super().get_context()
        services = []
        for config in apps.get_app_configs():
            if hasattr(config.module, 'NABAZTAG_SERVICE_PRIORITY'):
                services.append({
                    'priority': config.module.NABAZTAG_SERVICE_PRIORITY,
                    'name': config.name
                })
        services_sorted = sorted(services, key=lambda s: s['priority'])
        services_names = map(lambda s: s['name'], services_sorted)
        context["services"] = services_names
        return context

class NabWebSytemInfoView(BaseView):
    def template_name(self):
        return "nabweb/system-info/index.html"

    async def query_gestalt(self):
        try:
            conn = asyncio.open_connection('127.0.0.1', NabService.PORT_NUMBER)
            reader, writer = await asyncio.wait_for(conn, 0.5)
        except ConnectionRefusedError as err:
            return {"status":"error","message":"Nabd is not running"}
        except asyncio.TimeoutError as err:
            return {
                "status":"error",
                "message":"Communication with Nabd timed out (connecting)"
            }
        try:
            writer.write(b'{"type":"gestalt","request_id":"gestalt"}\r\n')
            while True:
                line = await asyncio.wait_for(reader.readline(), 0.5)
                packet = json.loads(line.decode("utf8"))
                if (
                    "type" in packet and
                    packet["type"] == "response" and
                    "request_id" in packet and
                    packet["request_id"] == "gestalt"
                ):
                    writer.close()
                    return {"status": "ok", "result": packet}
        except asyncio.TimeoutError as err:
            return {
                "status":"error",
                "message":"Communication with Nabd timed out (getting info)"
            }

    def get_os_info(self):
        version = "unknown"
        with open("/etc/os-release") as release:
            line = release.readline()
            matchObj = re.match(r'PRETTY_NAME="(.+)"$', line, re.M)
            if matchObj:
                version = matchObj.group(1)
        with open("/etc/rpi-issue") as issue:
            line = issue.readline()
            matchObj = re.search(r' ([0-9-]+)$', line, re.M)
            if matchObj:
                version = version + ', issue ' + matchObj.group(1)
        with open('/proc/uptime', 'r') as uptime_f:
            uptime = int(float(uptime_f.readline().split()[0]))
        return {'version': version, 'uptime': uptime}

    def get_context(self):
        context = super().get_context()
        gestalt = asyncio.run(self.query_gestalt())
        context["gestalt"] = gestalt
        context["os"] = self.get_os_info()
        return context

class NabWebUpgradeView(View):
    def get(self, request, *args, **kwargs):
        root_dir = (
            os.popen(
                "sed -nE -e 's|WorkingDirectory=(.+)|\\1|p' "
                "< /lib/systemd/system/nabd.service"
            )
            .read()
            .rstrip()
        )
        if root_dir == "":
            return JsonResponse(
                {
                    "status": "error",
                    "message": "Cannot find pynab installation from "
                    "Raspbian systemd services",
                }
            )
        head_sha1 = (
            os.popen(f"cd {root_dir} && git rev-parse HEAD").read().rstrip()
        )
        if head_sha1 == "":
            return JsonResponse(
                {
                    "status": "error",
                    "message": "Cannot get HEAD - not a git repository? "
                    "Check /var/log/syslog",
                }
            )
        commit_count = (
            os.popen(
                f"cd {root_dir} && git fetch "
                f"&& git rev-list --count HEAD..origin/master"
            )
            .read()
            .rstrip()
        )
        if commit_count == "":
            return JsonResponse(
                {
                    "status": "error",
                    "message": "Cannot get number of commits from upstream. "
                    "Not connected to the internet?",
                }
            )
        return JsonResponse(
            {"status": "ok", "head": head_sha1, "commit_count": commit_count}
        )

    def post(self, request, *args, **kwargs):
        root_dir = (
            os.popen(
                "sed -nE -e 's|WorkingDirectory=(.+)|\\1|p' "
                "< /lib/systemd/system/nabd.service"
            )
            .read()
            .rstrip()
        )
        head_sha1 = (
            os.popen(f"cd {root_dir} && git rev-parse HEAD").read().rstrip()
        )
        pid = os.fork()
        if pid == 0:  # new process
            os.system(f"nohup bash {root_dir}/upgrade.sh &")
            exit()
        return JsonResponse(
            {"status": "ok", "root_dir": root_dir, "old": head_sha1}
        )
