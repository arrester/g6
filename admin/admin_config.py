import re
import socket
from typing import List

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from core.database import db_session
from core.exception import AlertException
from core.formclass import ConfigForm
from core.models import Config
from core.template import AdminTemplates
from lib.common import get_client_ip, get_host_public_ip
from lib.dependency.dependencies import check_demo_alert, validate_super_admin, validate_token
from lib.template_functions import (
    get_editor_select, get_member_level_select, get_skin_select,
    get_member_id_select, 
)

router = APIRouter()
templates = AdminTemplates()
# 파이썬 함수 및 변수를 jinja2 에서 사용할 수 있도록 등록
templates.env.globals["get_member_id_select"] = get_member_id_select
templates.env.globals["get_skin_select"] = get_skin_select
templates.env.globals["get_editor_select"] = get_editor_select
templates.env.globals["get_member_level_select"] = get_member_level_select

CONFIG_MENU_KEY = "100100"


@router.get("/config_form")
async def config_form(request: Request, db: db_session):
    """
    기본환경설정 폼
    """
    request.session["menu_key"] = CONFIG_MENU_KEY

    host_name = socket.gethostname()
    host_ip = socket.gethostbyname(host_name)
    host_public_ip = await get_host_public_ip()
    client_ip = get_client_ip(request)

    # 데모모드
    config = db.scalars(select(Config)).first()
    config = conv_field_info(request, config, [
        'cf_admin_email', 'cf_cert_kcb_cd', 'cf_cert_kcp_cd', 'cf_icode_id',
        'cf_icode_pw', 'cf_facebook_appid', 'cf_facebook_secret',
        'cf_twitter_key', 'cf_twitter_secret', 'cf_googl_shorturl_apikey',
        'cf_naver_clientid', 'cf_naver_secret', 'cf_kakao_js_apikey',
        'cf_payco_clientid', 'cf_payco_secret', 'cf_lg_mid',
        'cf_lg_mert_key', 'cf_cert_kg_mid', 'cf_cert_kg_cd',
        'cf_recaptcha_site_key', 'cf_recaptcha_secret_key', 'cf_google_clientid',
        'cf_google_secret', 'cf_kakao_rest_key', 'cf_kakao_client_secret'])

    context = {
        "request": request,
        "config": config,
        "host_name": host_name,
        "host_ip": host_ip,
        "host_public_ip": host_public_ip,
        "client_ip": client_ip,
    }
    return templates.TemplateResponse("config_form.html", context)


@router.post("/config_form_update",
             dependencies=[Depends(check_demo_alert), Depends(validate_token)])
async def config_form_update(
    request: Request,
    db: db_session,
    social_list: List[str] = Form(None, alias="cf_social_servicelist[]"),
    form_data: ConfigForm = Depends(),
):
    """
    기본환경설정 저장
    """
    # 차단 IP 리스트에 현재 접속 IP 가 있으면 접속이 불가하게 되므로 저장하지 않는다.
    if form_data.cf_intercept_ip:
        client_ip = get_client_ip(request)
        pattern = form_data.cf_intercept_ip.split("\n")
        for i in range(len(pattern)):
            pattern[i] = pattern[i].strip()
            if not pattern[i]:
                continue
            pattern[i] = pattern[i].replace(".", r"\.")
            pattern[i] = pattern[i].replace("+", r"[0-9\.]+")
            if re.match(fr"^{pattern[i]}$", client_ip):
                raise AlertException("현재 접속 IP : " + client_ip + " 가 차단될수 있으므로 다른 IP를 입력해 주세요.")

    # 본인인증 설정 체크
    if (form_data.cf_cert_use 
        and not any([form_data.cf_cert_ipin, form_data.cf_cert_hp, form_data.cf_cert_simple])):
        raise AlertException("본인확인을 위해 아이핀, 휴대폰 본인확인, KG이니시스 간편인증 서비스 중 하나 이상 선택해 주십시오.")

    if not form_data.cf_cert_use:
        form_data.cf_cert_ipin = form_data.cf_cert_hp = form_data.cf_cert_simple = ""

    # 소셜로그인 설정
    # 배열로 넘어오는 자료를 문자열로 변환. 예) "naver,kakao,facebook,google,twitter,payco"
    form_data.cf_social_servicelist = ','.join(social_list) if social_list else ""

    # 폼 데이터 반영 후 commit
    config = db.scalars(select(Config)).one()
    for field, value in form_data.__dict__.items():
        setattr(config, field, value)
    db.commit()

    return RedirectResponse("/admin/config_form", status_code=303)
