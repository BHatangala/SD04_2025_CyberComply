# ──────────────────────────────────────────────────────────────────────────────
# utils.py — Organisational Email Validator
#
# Logic flow:
#   1. Canonicalise to lowercase, extract domain
#   2. DEV_WHITELIST check  → always allow (specific full emails only)
#   3. DISPOSABLE_BLACKLIST → reject (temp/throwaway services)
#   4. PERSONAL_BLACKLIST   → reject (consumer email providers)
#   5. Everything else      → accepted as organisational
#
# Import into views.py:
#   from .utils import validate_org_email
# ──────────────────────────────────────────────────────────────────────────────


# ── Dev / Admin team whitelist ────────────────────────────────────────────────
# Full email addresses only. These bypass ALL domain checks.
# Add your team members' personal emails here so they can request admin access
# during development and testing.
DEV_WHITELIST: set = {
    # Add dev/admin team emails below — exact lowercase match
    # e.g. "dev.lead@gmail.com",
    "suwarnadaranpathmanathan@gmail.com",
    "erandathiuthpalawanna@gmail.com", "ibrahimimthi41@gmail.com",
    "edirisinghev82oth@gmail.com", "bimsaradbh@gmail.com", "cybercomplyproject@gmail.com",
    "sehansamc@gmail.com", "ammaarmafaz@gmail.com",
}


# ── Disposable / temporary email services blacklist ───────────────────────────
# Known throwaway / temp-mail providers. Kept as a curated static list to avoid
# any external API dependency.
DISPOSABLE_BLACKLIST: set = {
    "mailinator.com", "guerrillamail.com", "guerrillamail.net", "guerrillamail.org",
    "guerrillamail.biz", "guerrillamail.de", "guerrillamail.info",
    "tempmail.com", "temp-mail.org", "temp-mail.io", "throwam.com",
    "throwaway.email", "dispostable.com", "discard.email", "discardmail.com",
    "discardmail.de", "mailnull.com", "spamgourmet.com", "spamgourmet.net",
    "spamgourmet.org", "trashmail.com", "trashmail.at", "trashmail.io",
    "trashmail.me", "trashmail.net", "trashmail.org", "trashmail.xyz",
    "yopmail.com", "yopmail.fr", "yopmail.net", "cool.fr.nf", "jetable.fr.nf",
    "nospam.ze.tc", "nomail.xl.cx", "mega.zik.dj", "speed.1s.fr",
    "courriel.fr.nf", "moncourrier.fr.nf", "monemail.fr.nf", "monmail.fr.nf",
    "maildrop.cc", "mailnesia.com", "mailnull.com", "spamfree24.org",
    "spamfree24.de", "spamfree24.eu", "spamfree24.info", "spamfree24.net",
    "spam4.me", "spamgob.com", "spamherelots.com", "spamhereplease.com",
    "spamoff.de", "spamspot.com", "spamthis.co.uk", "spamtroll.net",
    "speed.1s.fr", "suremail.info", "sweetxxx.de", "teleworm.us",
    "temporaryemail.net", "temporaryemail.us", "temporaryforwarding.com",
    "temporaryinbox.com", "thankyou2010.com", "thisisnotmyrealemail.com",
    "throwam.com", "tilien.com", "tmailinator.com", "trbvm.com",
    "turual.com", "twinmail.de", "tyldd.com", "uggsrock.com",
    "uroid.com", "webcammail.org", "wegwerfadresse.de", "wegwerfemail.de",
    "wegwerfemail.net", "wegwerfemail.org", "wegwerfmail.de", "wegwerfmail.info",
    "wegwerfmail.net", "wegwerfmail.org", "wetrainbayarea.com", "wilemail.com",
    "willselfdestruct.com", "wralawfirm.com", "wronghead.com",
    "www.e4ward.com", "xagloo.co", "xagloo.com", "xemaps.com",
    "xents.com", "xmaily.com", "xoxy.net", "xyzzy.eu",
    "yapped.net", "yeah.net", "yep.it", "yogamaven.com",
    "yomail.info", "ypmail.webarnak.fr.eu.org", "yuurok.com",
    "z1p.biz", "za.com", "zehnminuten.de", "zehnminutenmail.de",
    "zehnminutenmail.com", "zetmail.com", "zippymail.info", "zoemail.net",
    "zoemail.org", "zomg.info", "zxcv.com", "zxcvbnm.com",
    "zzz.com", "fakeinbox.com", "fakeinbox.net", "filzmail.com",
    "firedrive.com", "fixmail.tk", "fizmail.com", "fleckens.hu",
    "fmailbox.com", "fmailc.com", "fmailx.com", "fnmail.com",
    "frapmail.com", "freundin.ru", "fudgerub.com", "fux0ringduh.com",
    "getairmail.com", "getmails.eu", "getonemail.com", "getonemail.net",
    "gishpuppy.com", "gowikibooks.com", "gowikicampus.com", "gowikicars.com",
    "gowikifilms.com", "gowikigames.com", "gowikimail.com", "gowikimusic.com",
    "gowikinetwork.com", "gowikitravel.com", "gowikitv.com", "grandmamail.com",
    "great-host.in", "greensloth.com", "grr.la", "gsrv.co.uk",
    "guerillamail.biz", "guerillamail.com", "guerillamail.de",
    "guerillamail.info", "guerillamail.net", "guerillamail.org",
    "h8s.org", "haltospam.com", "hatespam.org", "hidemail.de",
    "hidzz.com", "hmamail.com", "hopemail.biz", "ieatspam.eu",
    "ieatspam.info", "ilovespam.com", "imails.info", "inboxalias.com",
    "inboxclean.com", "inboxclean.org", "infocom.zp.ua", "instant-mail.de",
    "ipoo.org", "irish2me.com", "iwi.net", "jetable.com",
    "jetable.fr.nf", "jetable.net", "jetable.org", "jnxjn.com",
    "junk1.tk", "jupimail.com", "just4fun.dk", "justicemail.com",
    "kasmail.com", "kaspop.com", "killmail.com", "killmail.net",
    "klassmaster.com", "klzlk.com", "koszmail.pl", "kurzepost.de",
    "letthemeatspam.com", "lhsdv.com", "lifebyfood.com", "link2mail.net",
    "litedrop.com", "lol.ovpn.to", "lolfreak.net", "lookugly.com",
    "lopl.co.cc", "lortemail.dk", "lovemeleaveme.com", "luckymail.org",
    "lux.bookmarky.at", "luxusmail.org", "lyfestylecoffin.com",
    "m21.cc", "mail-filter.com", "mail-temporaire.fr", "mail.by",
    "mail2rss.org", "mail333.com", "mailbucket.org", "mailcat.biz",
    "mailcatch.com", "maileater.com", "maileimer.de", "mailexpire.com",
    "mailfall.com", "mailfreeonline.com", "mailguard.me", "mailimate.com",
    "mailin8r.com", "mailinater.com", "mailismagic.com", "mailme.ir",
    "mailme.lv", "mailme24.com", "mailmetrash.com", "mailmoat.com",
    "mailnew.com", "mailnull.com", "mailpick.biz", "mailproxsy.com",
    "mailquack.com", "mailrock.biz", "mailscrap.com", "mailshell.com",
    "mailsiphon.com", "mailslite.com", "mailsource.info", "mailsss.net",
    "mailtemp.info", "mailtome.de", "mailtothis.com", "mailtrash.net",
    "mailtv.net", "mailtv.tv", "mailzilla.com", "mailzilla.org",
    "mbx.cc", "mega.zik.dj", "meinspamschutz.de", "meltmail.com",
    "messagebeamer.de", "mierdamail.com", "mintemail.com", "misterpinball.de",
    "mjukglass.nu", "mmmmail.com", "mobi.web.id", "mobileninja.co.uk",
    "moburl.com", "mohmal.com", "moncourrier.fr.nf", "monemail.fr.nf",
    "monmail.fr.nf", "msa.minsmail.com", "mt2009.com", "mt2014.com",
    "mx0.wwwnew.eu", "my10minutemail.com", "myalias.pw", "mycleaninbox.net",
    "myemailboxy.com", "mymail-in.net", "mymailoasis.com", "mynetstore.de",
    "myphantomemail.com", "myspaceinc.com", "myspaceinc.net", "myspacepimpedup.com",
    "myspamless.com", "mytemp.email", "mytempemail.com", "mytempmail.com",
    "mytrashmail.com", "nabuma.com", "neomailbox.com", "nepwk.com",
    "nervmich.net", "nervtmich.net", "netviewer-france.com", "nevermail.de",
    "newbpotato.tk", "nice-4u.com", "nincsmail.com", "nnh.com",
    "no-spam.ws", "noblepioneer.com", "nomail.pw", "nomail.xl.cx",
    "nomail2me.com", "nomorespamemails.com", "nonspam.eu", "nonspammer.de",
    "noref.in", "norseforce.com", "nospam.ze.tc", "nospamfor.us",
    "nospammail.net", "nospamthanks.info", "notmailinator.com", "nowhere.org",
    "nowmymail.com", "nurfuerspam.de", "nus.edu.sg", "nwldx.com",
    "o2.co.uk", "objectmail.com", "obobbo.com", "odaymail.com",
    "odnorazovoe.ru", "oneoffmail.com", "onewaymail.com", "online.ms",
    "onqin.com", "opayq.com", "opentrash.com", "ordinaryamerican.net",
    "otherinbox.comsafe-mail.net", "owlpic.com",
    "pancakemail.com", "paplease.com", "pcusers.otherinbox.com",
    "pepbot.com", "pfui.ru", "phreaker.net", "plexolan.de",
    "poczta.onet.pl", "politikerclub.de", "poofy.org", "pookmail.com",
    "pop3.xyz", "postacı.com", "postfach.cc", "proxymail.eu",
    "prtnx.com", "prtz.eu", "punkass.com", "putthisinyourspamdatabase.com",
    "qisdo.com", "qisoa.com", "qoika.com", "qq.com",
    "quickinbox.com", "quickmail.nl",
    "rcpt.at", "reallymymail.com", "recode.me", "recursor.net",
    "recyclemail.dk", "regbypass.com", "regbypass.comsafe-mail.net",
    "rejectmail.com", "reliable-mail.com", "rklips.com", "rmqkr.net",
    "rppkn.com", "rtrtr.com", "rumgel.com", "ruu.kr",
    "s0ny.net", "safe-mail.net", "safetymail.info", "safetypost.de",
    "sandelf.de", "saynotospams.com", "schrott-email.de", "secretemail.de",
    "secure-mail.biz", "selfdestructingmail.com", "sendspamhere.com",
    "sharklasers.com", "shieldedmail.com", "shiftmail.com", "shitmail.de",
    "shitmail.me", "shortmail.net", "showslow.de", "sibmail.com",
    "sinnlos-mail.de", "skeefmail.com", "slaskpost.se", "slopsbox.com",
    "slothmail.net", "smellfear.com", "snakemail.com", "sneakemail.com",
    "sneakmail.de", "snkmail.com", "sofimail.com", "sofort-mail.de",
    "sogetthis.com", "sohai.ml", "soodomail.com", "soodonims.com",
    "spam.la", "spam.mn", "spam.su", "spamavert.com",
    "spambob.com", "spambob.net", "spambob.org", "spambog.com",
    "spambog.de", "spambog.ru", "spambox.info", "spambox.us",
    "spamcannon.com", "spamcannon.net", "spamcero.com", "spamcon.org",
    "spamcorptastic.com", "spamcowboy.com", "spamcowboy.net",
    "spamcowboy.org", "spamday.com", "spamex.com",
    "guerrillamailblock.com", "tempinbox.com", "tempinbox.co.uk",
    "tempr.email", "tempsky.com", "temptome.com", "thankyou2010.com",
    "that.com", "the.cowsurf.com", "the18plus.com", "theinternetemail.com",
    "theinternetemail.net", "theplussers.net",
    "adguard.com", "abyssmail.com", "acroreader.xyz",
    "altmails.com", "anonymbox.com", "antispam24.de",
    "beefmilk.com", "binkmail.com", "bio-muesli.info",
    "bobmail.info", "bodhi.lawlita.com", "breakthru.com",
    "bspamfree.org", "buffemail.com", "bugmenot.com",
    "bumpymail.com", "buttmail.co.uk",
}


# ── Personal / consumer email provider blacklist ──────────────────────────────
# Common non-organisational email domains. Anything in this list is rejected
# when a user tries to register as Administrative or submit an admin access request.
PERSONAL_BLACKLIST: set = {
    # Google
    "gmail.com", "googlemail.com",
    # Microsoft
    "hotmail.com", "hotmail.co.uk", "hotmail.fr", "hotmail.de",
    "hotmail.es", "hotmail.it", "hotmail.com.au", "hotmail.ca",
    "hotmail.com.br", "hotmail.co.in", "hotmail.com.ar", "hotmail.com.mx",
    "outlook.com", "outlook.com.au", "outlook.co.uk", "outlook.fr",
    "outlook.de", "outlook.es", "outlook.it", "outlook.co.in",
    "live.com", "live.co.uk", "live.com.au", "live.ca", "live.fr",
    "live.de", "live.in", "live.com.ar", "live.com.mx", "live.it",
    "msn.com",
    # Yahoo
    "yahoo.com", "yahoo.co.uk", "yahoo.co.in", "yahoo.com.au",
    "yahoo.com.br", "yahoo.ca", "yahoo.fr", "yahoo.de", "yahoo.es",
    "yahoo.it", "yahoo.co.jp", "yahoo.com.ar", "yahoo.com.mx",
    "yahoo.com.ph", "yahoo.com.sg", "yahoo.co.id",
    "ymail.com", "rocketmail.com",
    # Apple
    "icloud.com", "me.com", "mac.com",
    # AOL / Verizon
    "aol.com", "aol.co.uk", "aim.com", "verizon.net", "compuserve.com",
    # Proton
    "protonmail.com", "protonmail.ch", "proton.me", "pm.me",
    # Others
    "zoho.com", "zohomail.com",
    "mail.com", "email.com", "usa.com", "myself.com", "consultant.com",
    "post.com", "dr.com", "writeme.com", "fastservice.com",
    "iname.com", "hushmail.com", "hush.com", "hush.ai",
    "inbox.com", "inboxmail.com",
    "fastmail.com", "fastmail.fm", "fastmail.cn", "fastmail.es",
    "fastmail.to", "fastmail.net", "fastmail.org", "fastmail.in",
    "fastmail.jp", "fastmail.us", "fastmail.co.uk", "fastmail.com.au",
    "gmx.com", "gmx.net", "gmx.de", "gmx.at", "gmx.ch",
    "gmx.us", "gmx.co.uk", "gmx.fr", "gmx.es", "gmx.it",
    "web.de", "t-online.de", "freenet.de", "arcor.de",
    "o2.pl", "wp.pl", "onet.pl", "interia.pl",
    "libero.it", "virgilio.it", "tin.it",
    "orange.fr", "sfr.fr", "free.fr", "wanadoo.fr", "laposte.net",
    "terra.com.br", "uol.com.br", "bol.com.br", "ig.com.br",
    "rediffmail.com", "indiatimes.com", "sify.com",
    "naver.com", "daum.net", "hanmail.net",
    "mail.ru", "list.ru", "inbox.ru", "bk.ru", "internet.ru",
    "rambler.ru", "yandex.ru", "yandex.com", "yandex.ua",
    "bigpond.com", "bigpond.net.au", "optusnet.com.au", "tpg.com.au",
    "rogers.com", "shaw.ca", "telus.net", "sympatico.ca",
    "btinternet.com", "btopenworld.com", "blueyonder.co.uk",
    "virginmedia.com", "talktalk.net", "sky.com", "ntlworld.com",
    "cox.net", "sbcglobal.net", "bellsouth.net", "att.net",
    "comcast.net", "charter.net", "earthlink.net", "roadrunner.com",
    "optonline.net", "juno.com", "netzero.com", "netzero.net",
    "lycos.com", "lycos.co.uk",
    "excite.com", "excite.co.uk",
    "tutanota.com", "tutanota.de", "tutamail.com", "tuta.io",
    "mailfence.com",
    "startmail.com",
    "runbox.com",
    "posteo.net", "posteo.de",
    "cock.li", "airmail.cc", "420blaze.it",
    "disroot.org",
    "riseup.net",
}


def validate_org_email(email: str) -> "tuple[bool, str | None]":
    """
    Validates whether an email address belongs to an organisational domain.

    Returns:
        (True, None)          — email is accepted as organisational
        (False, error_message) — email is rejected; error_message explains why

    Usage:
        is_valid, error = validate_org_email(email)
        if not is_valid:
            return JsonResponse({"detail": error}, status=400)
    """
    if not email or not isinstance(email, str):
        return False, "A valid email address is required."

    email = email.strip().lower()

    # Must contain exactly one @ with content on both sides
    parts = email.split("@")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return False, "Please enter a valid email address."

    domain = parts[1]

    # Must have at least one dot in the domain
    if "." not in domain:
        return False, "Please enter a valid email address."

    # ── Step 1: Whitelist — dev/admin team override ───────────────────────────
    if email in DEV_WHITELIST:
        return True, None

    # ── Step 2: Disposable email check ───────────────────────────────────────
    if domain in DISPOSABLE_BLACKLIST:
        return False, "Disposable or temporary email addresses are not permitted. Please use your organisation email."

    # ── Step 3: Personal email check ─────────────────────────────────────────
    if domain in PERSONAL_BLACKLIST:
        return False, "Personal email addresses are not permitted for administrative access. Please use your organisation email."

    # ── Step 4: Pass — treat as organisational ────────────────────────────────
    return True, None