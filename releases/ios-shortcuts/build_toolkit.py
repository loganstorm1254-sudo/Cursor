#!/usr/bin/env python3
"""Build and HubSign the iOS Toolkit shortcut (and optional invert helpers)."""

from __future__ import annotations

import argparse
import json
import plistlib
import uuid
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
HUBSIGN_URL = "https://hubsign.routinehub.services/sign"
HUBSIGN_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "cherri/1.0",
    "Origin": "https://routinehub.co",
    "Referer": "https://routinehub.co/",
}

INPUT_CLASSES = [
    "WFAppStoreAppContentItem",
    "WFArticleContentItem",
    "WFContactContentItem",
    "WFDateContentItem",
    "WFEmailAddressContentItem",
    "WFGenericFileContentItem",
    "WFImageContentItem",
    "WFiTunesProductContentItem",
    "WFLocationContentItem",
    "WFDCMapsLinkContentItem",
    "WFAVAssetContentItem",
    "WFPDFContentItem",
    "WFPhoneNumberContentItem",
    "WFRichTextContentItem",
    "WFSafariWebPageContentItem",
    "WFStringContentItem",
    "WFURLContentItem",
]

# Icon: teal toolbox vibe
TOOLKIT_ICON = {
    "WFWorkflowIconStartColor": 431817727,  # teal
    "WFWorkflowIconGlyphNumber": 59511,  # wrench-ish / gear family
}


def uid() -> str:
    return str(uuid.uuid4()).upper()


def action(identifier: str, params: dict | None = None) -> dict:
    return {
        "WFWorkflowActionIdentifier": identifier,
        "WFWorkflowActionParameters": params or {},
    }


def wf(identifier: str, params: dict | None = None) -> dict:
    return action(f"is.workflow.actions.{identifier}", params)


def ax_toggle(intent: str) -> dict:
    return action(
        f"com.apple.AccessibilityUtilities.AXSettingsShortcuts.{intent}",
        {"operation": "toggle", "UUID": uid()},
    )


def sys_toggle(identifier: str, extra: dict | None = None) -> dict:
    params = {"operation": "toggle", "UUID": uid()}
    if extra:
        params.update(extra)
    return wf(identifier, params)


def menu_start(group: str, prompt: str, items: list[str]) -> dict:
    return wf(
        "choosefrommenu",
        {
            "UUID": uid(),
            "GroupingIdentifier": group,
            "WFControlFlowMode": 0,
            "WFMenuPrompt": prompt,
            "WFMenuItems": items,
        },
    )


def menu_case(group: str, title: str) -> dict:
    return wf(
        "choosefrommenu",
        {
            "UUID": uid(),
            "GroupingIdentifier": group,
            "WFControlFlowMode": 1,
            "WFMenuItemTitle": title,
        },
    )


def menu_end(group: str) -> dict:
    return wf(
        "choosefrommenu",
        {
            "UUID": uid(),
            "GroupingIdentifier": group,
            "WFControlFlowMode": 2,
        },
    )


def action_output(output_uuid: str, name: str) -> dict:
    return {"Type": "ActionOutput", "OutputUUID": output_uuid, "OutputName": name}


def attachment(att: dict) -> dict:
    return {"Value": att, "WFSerializationType": "WFTextTokenAttachment"}


def text(*parts) -> dict:
    string, ranges = "", {}
    for part in parts:
        if isinstance(part, str):
            string += part
        else:
            ranges[f"{{{len(string)}, 1}}"] = part
            string += "\ufffc"
    return {
        "Value": {"string": string, "attachmentsByRange": ranges},
        "WFSerializationType": "WFTextTokenString",
    }


def show_result(*parts) -> dict:
    return wf("showresult", {"Text": text(*parts)})


def notify(title: str, *body_parts) -> dict:
    return wf(
        "notification",
        {
            "WFNotificationActionTitle": title,
            "WFNotificationActionBody": text(*body_parts) if body_parts else title,
        },
    )


def open_url(url: str) -> list[dict]:
    u = uid()
    return [
        wf("url", {"UUID": u, "WFURLActionURL": url}),
        wf("openurl", {"WFInput": attachment(action_output(u, "URL"))}),
    ]


def ask_text(prompt: str, default: str = "") -> tuple[str, dict]:
    u = uid()
    params = {
        "UUID": u,
        "WFAskActionPrompt": prompt,
        "WFInputType": "Text",
    }
    if default:
        params["WFAskActionDefaultAnswer"] = default
    return u, wf("ask", params)


def set_clipboard_from(output_uuid: str, name: str) -> dict:
    return wf("setclipboard", {"WFInput": attachment(action_output(output_uuid, name))})


def workflow(actions: list[dict], icon: dict | None = None) -> dict:
    return {
        "WFWorkflowClientVersion": "1505.3",
        "WFWorkflowMinimumClientVersion": 900,
        "WFWorkflowMinimumClientVersionString": "900",
        "WFWorkflowIcon": icon or TOOLKIT_ICON,
        "WFWorkflowImportQuestions": [],
        "WFWorkflowTypes": ["NCWidget", "WatchKit"],
        "WFWorkflowInputContentItemClasses": INPUT_CLASSES,
        "WFWorkflowOutputContentItemClasses": [],
        "WFWorkflowHasOutputFallback": False,
        "WFQuickActionSurfaces": [],
        "WFWorkflowHasShortcutInputVariables": False,
        "WFWorkflowActions": actions,
    }


def build_accessibility_submenu() -> list[dict]:
    g = uid()
    items = [
        "Classic Invert",
        "Smart Invert",
        "Color Filters",
        "Reduce Motion",
        "Reduce Transparency",
        "Increase Contrast",
        "White Point",
        "AssistiveTouch",
        "Zoom",
        "Live Captions",
        "Voice Control",
        "Mono Audio",
    ]
    intents = {
        "Classic Invert": "AXToggleClassicInvertIntent",
        "Smart Invert": "AXToggleSmartInvertIntent",
        "Color Filters": "AXToggleColorFiltersIntent",
        "Reduce Motion": "AXToggleReduceMotionIntent",
        "Reduce Transparency": "AXToggleTransparencyIntent",
        "Increase Contrast": "AXToggleContrastIntent",
        "White Point": "AXToggleWhitePointIntent",
        "AssistiveTouch": "AXToggleAssistiveTouchIntent",
        "Zoom": "AXToggleZoomIntent",
        "Live Captions": "AXToggleLiveCaptionsIntent",
        "Voice Control": "AXToggleVoiceControlIntent",
        "Mono Audio": "AXToggleMonoAudioIntent",
    }
    out = [menu_start(g, "Accessibility", items)]
    for title in items:
        out.append(menu_case(g, title))
        out.append(ax_toggle(intents[title]))
    out.append(menu_end(g))
    return out


def build_controls_submenu() -> list[dict]:
    g = uid()
    items = [
        "Flashlight",
        "Dark Mode",
        "Low Power Mode",
        "Orientation Lock",
        "True Tone",
        "Night Shift",
        "Always On Display",
        "Wi-Fi",
        "Bluetooth",
        "Airplane Mode",
        "Cellular Data",
        "Personal Hotspot",
        "Brightness 50%",
        "Brightness Ask",
        "Volume Ask",
        "Lock Screen",
        "Vibrate",
    ]
    out = [menu_start(g, "Controls", items)]

    toggles = {
        "Flashlight": ("flashlight", None),
        "Dark Mode": ("appearance", {"style": "dark"}),
        "Low Power Mode": ("lowpowermode.set", None),
        "Orientation Lock": ("orientationlock.set", None),
        "True Tone": ("truetone.set", None),
        "Night Shift": ("nightshift.set", None),
        "Always On Display": ("display.always-on.set", None),
        "Wi-Fi": ("wifi.set", None),
        "Bluetooth": ("bluetooth.set", None),
        "Airplane Mode": ("airplanemode.set", None),
        "Cellular Data": ("cellulardata.set", None),
        "Personal Hotspot": ("personalhotspot.set", None),
    }

    for title in items:
        out.append(menu_case(g, title))
        if title in toggles:
            ident, extra = toggles[title]
            out.append(sys_toggle(ident, extra))
        elif title == "Brightness 50%":
            out.append(wf("setbrightness", {"WFBrightness": 0.5, "UUID": uid()}))
        elif title == "Brightness Ask":
            ask_u, ask_a = ask_text("Brightness 0–1 (e.g. 0.5)", "0.5")
            out.append(ask_a)
            num_u = uid()
            out.append(
                wf(
                    "number",
                    {
                        "UUID": num_u,
                        "WFNumberActionNumber": attachment(
                            action_output(ask_u, "Provided Input")
                        ),
                    },
                )
            )
            out.append(
                wf(
                    "setbrightness",
                    {
                        "UUID": uid(),
                        "WFBrightness": attachment(action_output(num_u, "Number")),
                    },
                )
            )
        elif title == "Volume Ask":
            ask_u, ask_a = ask_text("Volume 0–1 (e.g. 0.5)", "0.5")
            out.append(ask_a)
            num_u = uid()
            out.append(
                wf(
                    "number",
                    {
                        "UUID": num_u,
                        "WFNumberActionNumber": attachment(
                            action_output(ask_u, "Provided Input")
                        ),
                    },
                )
            )
            out.append(
                wf(
                    "setvolume",
                    {
                        "UUID": uid(),
                        "WFVolume": attachment(action_output(num_u, "Number")),
                    },
                )
            )
        elif title == "Lock Screen":
            out.append(wf("lockscreen", {"UUID": uid()}))
        elif title == "Vibrate":
            out.append(wf("vibrate", {"UUID": uid()}))
    out.append(menu_end(g))
    return out


def build_clipboard_submenu() -> list[dict]:
    g = uid()
    items = [
        "Show Clipboard",
        "Clear Clipboard",
        "Copy Battery %",
        "Copy Device Name",
        "Copy System Version",
        "Copy Model",
        "Copy Network Name",
        "Copy Public IP",
    ]
    out = [menu_start(g, "Clipboard & Device", items)]

    out.append(menu_case(g, "Show Clipboard"))
    clip_u = uid()
    out.append(wf("getclipboard", {"UUID": clip_u}))
    out.append(show_result(action_output(clip_u, "Clipboard")))

    out.append(menu_case(g, "Clear Clipboard"))
    empty_u = uid()
    out.append(wf("gettext", {"UUID": empty_u, "WFTextActionText": ""}))
    out.append(set_clipboard_from(empty_u, "Text"))
    out.append(notify("Clipboard", "Cleared"))

    out.append(menu_case(g, "Copy Battery %"))
    bat_u = uid()
    out.append(wf("getbatterylevel", {"UUID": bat_u}))
    out.append(set_clipboard_from(bat_u, "Battery Level"))
    out.append(notify("Battery", action_output(bat_u, "Battery Level"), "% copied"))

    detail_map = {
        "Copy Device Name": "Device Name",
        "Copy System Version": "System Version",
        "Copy Model": "Device Model",
        "Copy Network Name": "Network Name",
    }
    for title, detail in detail_map.items():
        out.append(menu_case(g, title))
        d_u = uid()
        out.append(
            wf(
                "getdevicedetails",
                {"UUID": d_u, "WFDeviceDetail": detail},
            )
        )
        out.append(set_clipboard_from(d_u, "Device Details"))
        out.append(notify(detail, action_output(d_u, "Device Details")))

    out.append(menu_case(g, "Copy Public IP"))
    ip_u = uid()
    out.append(
        wf(
            "getipaddress",
            {
                "UUID": ip_u,
                "WFIPAddressSourceOption": "Public",
                "WFIPAddressTypeOption": "IPv4",
            },
        )
    )
    out.append(set_clipboard_from(ip_u, "IP Address"))
    out.append(notify("Public IP", action_output(ip_u, "IP Address")))

    out.append(menu_end(g))
    return out


def build_text_submenu() -> list[dict]:
    g = uid()
    items = [
        "UPPERCASE",
        "lowercase",
        "Title Case",
        "Count Characters",
        "Count Words",
        "Base64 Encode",
        "Base64 Decode",
        "URL Encode",
        "URL Decode",
        "SHA256 Hash",
        "Generate UUID",
        "Generate Password",
    ]
    out = [menu_start(g, "Text Tools", items)]

    case_map = {
        "UPPERCASE": "UPPERCASE",
        "lowercase": "lowercase",
        "Title Case": "Capitalize Every Word",
    }
    for title, case_type in case_map.items():
        out.append(menu_case(g, title))
        ask_u, ask_a = ask_text("Text to convert")
        out.append(ask_a)
        case_u = uid()
        out.append(
            wf(
                "text.changecase",
                {
                    "UUID": case_u,
                    "WFCaseType": case_type,
                    "text": attachment(action_output(ask_u, "Provided Input")),
                },
            )
        )
        out.append(set_clipboard_from(case_u, "Text"))
        out.append(show_result(action_output(case_u, "Text")))

    for title, count_type in (("Count Characters", "Characters"), ("Count Words", "Words")):
        out.append(menu_case(g, title))
        ask_u, ask_a = ask_text("Text to count")
        out.append(ask_a)
        c_u = uid()
        out.append(
            wf(
                "count",
                {
                    "UUID": c_u,
                    "WFCountType": count_type,
                    "Input": attachment(action_output(ask_u, "Provided Input")),
                },
            )
        )
        out.append(show_result(action_output(c_u, "Count")))

    for title, mode in (("Base64 Encode", "Encode"), ("Base64 Decode", "Decode")):
        out.append(menu_case(g, title))
        ask_u, ask_a = ask_text(f"Text to {mode.lower()}")
        out.append(ask_a)
        b_u = uid()
        out.append(
            wf(
                "base64encode",
                {
                    "UUID": b_u,
                    "WFEncodeMode": mode,
                    "WFInput": attachment(action_output(ask_u, "Provided Input")),
                },
            )
        )
        out.append(set_clipboard_from(b_u, "Base64 Encoded"))
        out.append(show_result(action_output(b_u, "Base64 Encoded")))

    out.append(menu_case(g, "URL Encode"))
    ask_u, ask_a = ask_text("Text to URL-encode")
    out.append(ask_a)
    e_u = uid()
    out.append(
        wf(
            "urlencode",
            {
                "UUID": e_u,
                "WFInput": attachment(action_output(ask_u, "Provided Input")),
            },
        )
    )
    out.append(set_clipboard_from(e_u, "URL Encoded Text"))
    out.append(show_result(action_output(e_u, "URL Encoded Text")))

    out.append(menu_case(g, "URL Decode"))
    ask_u, ask_a = ask_text("Text to URL-decode")
    out.append(ask_a)
    d_u = uid()
    out.append(
        wf(
            "urlencode",
            {
                "UUID": d_u,
                "WFEncodeMode": "Decode",
                "WFInput": attachment(action_output(ask_u, "Provided Input")),
            },
        )
    )
    out.append(set_clipboard_from(d_u, "URL Encoded Text"))
    out.append(show_result(action_output(d_u, "URL Encoded Text")))

    out.append(menu_case(g, "SHA256 Hash"))
    ask_u, ask_a = ask_text("Text to hash")
    out.append(ask_a)
    h_u = uid()
    out.append(
        wf(
            "hash",
            {
                "UUID": h_u,
                "WFHashType": "SHA256",
                "WFInput": attachment(action_output(ask_u, "Provided Input")),
            },
        )
    )
    out.append(set_clipboard_from(h_u, "Hash"))
    out.append(show_result(action_output(h_u, "Hash")))

    out.append(menu_case(g, "Generate UUID"))
    uuid_u = uid()
    out.append(
        wf(
            "downloadurl",
            {
                "UUID": uuid_u,
                "WFURL": "https://www.uuidtools.com/api/generate/v4/count/1",
                "WFHTTPMethod": "GET",
            },
        )
    )
    # API returns JSON array ["uuid"] — show raw + copy
    out.append(set_clipboard_from(uuid_u, "Contents of URL"))
    out.append(show_result(action_output(uuid_u, "Contents of URL")))

    out.append(menu_case(g, "Generate Password"))
    pw_u = uid()
    out.append(
        wf(
            "downloadurl",
            {
                "UUID": pw_u,
                "WFURL": (
                    "https://www.random.org/strings/"
                    "?num=1&len=20&digits=on&upperalpha=on&loweralpha=on"
                    "&unique=on&format=plain&rnd=new"
                ),
                "WFHTTPMethod": "GET",
            },
        )
    )
    out.append(set_clipboard_from(pw_u, "Contents of URL"))
    out.append(show_result(action_output(pw_u, "Contents of URL")))

    out.append(menu_end(g))
    return out


def build_time_submenu() -> list[dict]:
    g = uid()
    items = [
        "Show Date & Time",
        "Copy ISO 8601",
        "Copy Unix Timestamp",
        "Timer 5 min",
        "Timer 10 min",
        "Timer 25 min (Pomodoro)",
        "Toggle Focus",
        "Get Current Focus",
    ]
    out = [menu_start(g, "Time & Focus", items)]

    out.append(menu_case(g, "Show Date & Time"))
    date_u = uid()
    out.append(wf("date", {"UUID": date_u, "WFDateActionMode": "Current Date"}))
    out.append(show_result(action_output(date_u, "Date")))

    out.append(menu_case(g, "Copy ISO 8601"))
    date_u = uid()
    out.append(wf("date", {"UUID": date_u, "WFDateActionMode": "Current Date"}))
    fmt_u = uid()
    out.append(
        wf(
            "format.date",
            {
                "UUID": fmt_u,
                "WFDateFormatStyle": "ISO 8601",
                "WFDate": attachment(action_output(date_u, "Date")),
            },
        )
    )
    out.append(set_clipboard_from(fmt_u, "Formatted Date"))
    out.append(show_result(action_output(fmt_u, "Formatted Date")))

    out.append(menu_case(g, "Copy Unix Timestamp"))
    ts_u = uid()
    out.append(
        wf(
            "downloadurl",
            {
                "UUID": ts_u,
                "WFURL": "https://worldtimeapi.org/api/timezone/Etc/UTC",
                "WFHTTPMethod": "GET",
            },
        )
    )
    key_u = uid()
    out.append(
        wf(
            "getvalueforkey",
            {
                "UUID": key_u,
                "WFGetDictionaryValueType": "Value",
                "WFDictionaryKey": "unixtime",
                "WFInput": attachment(action_output(ts_u, "Contents of URL")),
            },
        )
    )
    out.append(set_clipboard_from(key_u, "Dictionary Value"))
    out.append(show_result(action_output(key_u, "Dictionary Value")))

    for title, minutes in (
        ("Timer 5 min", 5),
        ("Timer 10 min", 10),
        ("Timer 25 min (Pomodoro)", 25),
    ):
        out.append(menu_case(g, title))
        # Open Clock timer URL scheme with minutes prefilled when possible;
        # fall back to starting a Shortcuts timer duration in seconds.
        out.append(
            wf(
                "timer.start",
                {
                    "UUID": uid(),
                    "WFDuration": minutes * 60,
                },
            )
        )

    out.append(menu_case(g, "Toggle Focus"))
    out.append(sys_toggle("dnd.set"))

    out.append(menu_case(g, "Get Current Focus"))
    focus_u = uid()
    out.append(wf("dnd.getfocus", {"UUID": focus_u}))
    out.append(show_result(action_output(focus_u, "Focus Mode")))

    out.append(menu_end(g))
    return out


def build_network_submenu() -> list[dict]:
    g = uid()
    items = [
        "Show Public IP",
        "Show Local IP",
        "Show Wi-Fi Details",
        "Speedtest",
        "Down for Everyone?",
        "WhatsMyIP",
        "DNS Google",
        "Cloudflare 1.1.1.1",
    ]
    out = [menu_start(g, "Network", items)]

    out.append(menu_case(g, "Show Public IP"))
    ip_u = uid()
    out.append(
        wf(
            "getipaddress",
            {
                "UUID": ip_u,
                "WFIPAddressSourceOption": "Public",
                "WFIPAddressTypeOption": "IPv4",
            },
        )
    )
    out.append(show_result(action_output(ip_u, "IP Address")))

    out.append(menu_case(g, "Show Local IP"))
    ip_u = uid()
    out.append(
        wf(
            "getipaddress",
            {
                "UUID": ip_u,
                "WFIPAddressSourceOption": "Local",
                "WFIPAddressTypeOption": "IPv4",
            },
        )
    )
    out.append(show_result(action_output(ip_u, "IP Address")))

    out.append(menu_case(g, "Show Wi-Fi Details"))
    wifi_u = uid()
    out.append(wf("getwifi", {"UUID": wifi_u}))
    out.append(show_result(action_output(wifi_u, "Network Details")))

    links = {
        "Speedtest": "https://www.speedtest.net",
        "Down for Everyone?": "https://downforeveryoneorjustme.com",
        "WhatsMyIP": "https://api.ipify.org",
        "DNS Google": "https://dns.google",
        "Cloudflare 1.1.1.1": "https://one.one.one.one",
    }
    for title, url in links.items():
        out.append(menu_case(g, title))
        out.extend(open_url(url))

    out.append(menu_end(g))
    return out


def build_media_submenu() -> list[dict]:
    g = uid()
    items = [
        "Take Screenshot",
        "Take Photo",
        "Take Video",
        "Shazam",
        "Latest Photo",
        "Latest Screenshot",
    ]
    out = [menu_start(g, "Media", items)]

    out.append(menu_case(g, "Take Screenshot"))
    out.append(wf("takescreenshot", {"UUID": uid()}))

    out.append(menu_case(g, "Take Photo"))
    out.append(wf("takephoto", {"UUID": uid(), "WFCameraCaptureShowCameraPreview": True}))

    out.append(menu_case(g, "Take Video"))
    out.append(wf("takevideo", {"UUID": uid()}))

    out.append(menu_case(g, "Shazam"))
    shazam_u = uid()
    out.append(wf("shazammedia", {"UUID": shazam_u}))
    out.append(show_result(action_output(shazam_u, "Media")))

    out.append(menu_case(g, "Latest Photo"))
    photo_u = uid()
    out.append(wf("getlastphoto", {"UUID": photo_u, "WFGetLatestPhotoCount": 1}))
    out.append(
        wf(
            "previewdocument",
            {
                "UUID": uid(),
                "WFInput": attachment(action_output(photo_u, "Photos")),
            },
        )
    )

    out.append(menu_case(g, "Latest Screenshot"))
    shot_u = uid()
    out.append(wf("getlastscreenshot", {"UUID": shot_u, "WFGetLatestPhotoCount": 1}))
    out.append(
        wf(
            "previewdocument",
            {
                "UUID": uid(),
                "WFInput": attachment(action_output(shot_u, "Photos")),
            },
        )
    )

    out.append(menu_end(g))
    return out


def build_settings_submenu() -> list[dict]:
    g = uid()
    items = [
        "Settings Root",
        "Accessibility",
        "Wi-Fi",
        "Bluetooth",
        "Battery",
        "Display",
        "Focus",
        "Sounds",
        "General",
        "VPN",
        "Cellular",
        "Wallpaper",
        "Shortcuts",
        "App Store",
        "Home Screen",
    ]
    urls = {
        "Settings Root": "App-prefs:",
        "Accessibility": "App-prefs:ACCESSIBILITY",
        "Wi-Fi": "App-prefs:WIFI",
        "Bluetooth": "App-prefs:Bluetooth",
        "Battery": "App-prefs:BATTERY_USAGE",
        "Display": "App-prefs:DISPLAY",
        "Focus": "App-prefs:DO_NOT_DISTURB",
        "Sounds": "App-prefs:Sounds",
        "General": "App-prefs:General",
        "VPN": "App-prefs:General&path=VPN",
        "Cellular": "App-prefs:MOBILE_DATA_SETTINGS_ID",
        "Wallpaper": "App-prefs:Wallpaper",
        "Shortcuts": "shortcuts://",
        "App Store": "itms-apps://itunes.apple.com",
    }
    out = [menu_start(g, "Quick Open", items)]
    for title in items:
        out.append(menu_case(g, title))
        if title == "Home Screen":
            out.append(wf("returntohomescreen", {"UUID": uid()}))
        else:
            out.extend(open_url(urls[title]))
    out.append(menu_end(g))
    return out


def build_toolkit() -> dict:
    root = uid()
    categories = [
        "Accessibility",
        "Controls",
        "Clipboard & Device",
        "Text Tools",
        "Time & Focus",
        "Network",
        "Media",
        "Quick Open",
    ]
    builders = {
        "Accessibility": build_accessibility_submenu,
        "Controls": build_controls_submenu,
        "Clipboard & Device": build_clipboard_submenu,
        "Text Tools": build_text_submenu,
        "Time & Focus": build_time_submenu,
        "Network": build_network_submenu,
        "Media": build_media_submenu,
        "Quick Open": build_settings_submenu,
    }

    actions: list[dict] = [
        wf(
            "comment",
            {
                "WFCommentActionText": (
                    "iOS Toolkit — one menu for accessibility, controls, clipboard, "
                    "text, timers, network, media, and Settings deep links. "
                    "Add to Home Screen or the Shortcuts widget for quick access."
                )
            },
        ),
        menu_start(root, "iOS Toolkit", categories),
    ]
    for title in categories:
        actions.append(menu_case(root, title))
        actions.extend(builders[title]())
    actions.append(menu_end(root))
    return workflow(actions)


def build_invert(kind: str) -> dict:
    intent = (
        "AXToggleClassicInvertIntent"
        if kind == "classic"
        else "AXToggleSmartInvertIntent"
    )
    return workflow(
        [ax_toggle(intent)],
        icon={
            "WFWorkflowIconStartColor": 2846468607,
            "WFWorkflowIconGlyphNumber": 59829,
        },
    )


def sign(shortcut_plist: dict, name: str) -> bytes:
    xml = plistlib.dumps(shortcut_plist, fmt=plistlib.FMT_XML).decode()
    payload = json.dumps({"shortcutName": name, "shortcut": xml}).encode()
    req = Request(HUBSIGN_URL, data=payload, headers=HUBSIGN_HEADERS, method="POST")
    with urlopen(req, timeout=120) as resp:
        data = resp.read()
    if data[:4] != b"AEA1":
        raise RuntimeError(f"HubSign returned bad magic: {data[:4]!r}")
    return data


def write_outputs(name: str, pl: dict, *, do_sign: bool) -> None:
    unsigned = ROOT / f"{name}.unsigned.shortcut"
    with open(unsigned, "wb") as f:
        plistlib.dump(pl, f, fmt=plistlib.FMT_BINARY)
    print(f"wrote {unsigned} ({unsigned.stat().st_size} bytes)")

    xml_path = ROOT / f"{name}.xml"
    with open(xml_path, "wb") as f:
        plistlib.dump(pl, f, fmt=plistlib.FMT_XML)
    print(f"wrote {xml_path}")

    if do_sign:
        signed = sign(pl, name.replace("-", " "))
        out = ROOT / f"{name}.shortcut"
        out.write_bytes(signed)
        print(f"wrote {out} ({len(signed)} bytes, signed)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-sign", action="store_true")
    parser.add_argument(
        "--only",
        choices=["toolkit", "classic", "smart", "all"],
        default="all",
    )
    args = parser.parse_args()
    do_sign = not args.no_sign

    if args.only in ("toolkit", "all"):
        write_outputs("iOS-Toolkit", build_toolkit(), do_sign=do_sign)
    if args.only in ("classic", "all"):
        write_outputs("Toggle-Color-Invert", build_invert("classic"), do_sign=do_sign)
    if args.only in ("smart", "all"):
        write_outputs("Toggle-Smart-Invert", build_invert("smart"), do_sign=do_sign)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
