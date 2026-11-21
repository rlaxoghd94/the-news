<?php
/**
 * Plugin Name: The News — application passwords over HTTP
 * Description: 사이트가 Tailscale·WireGuard 안에서만 열리는 HTTP 홈랩 사이트라서, HTTPS가 아니어도 애플리케이션 비밀번호를 쓸 수 있게 합니다. publisher의 REST API 발행에 필요합니다.
 *
 * @package the-news
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

add_filter( 'wp_is_application_passwords_available', '__return_true' );
