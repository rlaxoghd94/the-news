<?php
/**
 * Plugin Name: The News — persona comments
 * Description: commenter 프로필이 페르소나 이름으로 댓글을 다는 REST 엔드포인트(the-news/v1), 페르소나 사용자 동기화, 페르소나 아바타를 제공합니다. 댓글 등록 계정에는 글 수정 권한 없이 tn_comments 권한만 줍니다.
 *
 * @package the-news
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

const TN_COMMENTS_CAP     = 'tn_comments';
const TN_COMMENTS_ROLE    = 'tn_commenter';
const TN_PERSONA_PREFIX   = 'persona-';
const TN_PERSONA_DOMAIN   = 'personas.the-news.invalid';
const TN_MAX_CONTENT_CHARS = 2000;

/*
 * Role: read + tn_comments only. No edit_posts / moderate_comments, so the account
 * cannot touch posts or other comments. Administrators also get tn_comments.
 */
add_action(
	'init',
	function () {
		$role = get_role( TN_COMMENTS_ROLE );
		if ( ! $role ) {
			$role = add_role( TN_COMMENTS_ROLE, 'The News commenter', array( 'read' => true ) );
		}
		if ( $role && ! $role->has_cap( TN_COMMENTS_CAP ) ) {
			$role->add_cap( TN_COMMENTS_CAP );
		}
		$admin = get_role( 'administrator' );
		if ( $admin && ! $admin->has_cap( TN_COMMENTS_CAP ) ) {
			$admin->add_cap( TN_COMMENTS_CAP );
		}
	}
);

/** Persona ID of a user, or '' for a normal user. */
function tn_persona_of_user( $user_id ) {
	return $user_id ? (string) get_user_meta( (int) $user_id, 'tn_persona', true ) : '';
}

/** Map persona ID => WP_User for every persona user. */
function tn_persona_users() {
	$users = get_users(
		array(
			'meta_key' => 'tn_persona',
			'number'   => -1,
		)
	);
	$out = array();
	foreach ( $users as $user ) {
		$out[ tn_persona_of_user( $user->ID ) ] = $user;
	}
	return $out;
}

function tn_comment_payload( WP_Comment $c ) {
	return array(
		'id'        => (int) $c->comment_ID,
		'parent'    => (int) $c->comment_parent,
		'author'    => $c->comment_author,
		'user_id'   => (int) $c->user_id,
		'date_gmt'  => mysql_to_rfc3339( $c->comment_date_gmt ),
		'status'    => wp_get_comment_status( $c ),
		'content'   => $c->comment_content,
		'generated' => (bool) get_comment_meta( $c->comment_ID, '_tn_generated', true ),
		'persona'   => (string) get_comment_meta( $c->comment_ID, '_tn_persona', true ),
		'card'      => (string) get_comment_meta( $c->comment_ID, '_tn_card', true ),
		'ref'       => (string) get_comment_meta( $c->comment_ID, '_tn_ref', true ),
	);
}

function tn_find_generated( $post_id, $card, $ref ) {
	$found = get_comments(
		array(
			'post_id'    => $post_id,
			'status'     => 'all',
			'number'     => 1,
			'meta_query' => array(
				array( 'key' => '_tn_card', 'value' => $card ),
				array( 'key' => '_tn_ref', 'value' => $ref ),
			),
		)
	);
	return $found ? $found[0] : null;
}

add_action(
	'rest_api_init',
	function () {
		$can = function () {
			return current_user_can( TN_COMMENTS_CAP );
		};

		// Persona list: persona ID => user.
		register_rest_route(
			'the-news/v1',
			'/personas',
			array(
				array(
					'methods'             => 'GET',
					'permission_callback' => $can,
					'callback'            => function () {
						$out = array();
						foreach ( tn_persona_users() as $pid => $user ) {
							$out[] = array(
								'persona'  => $pid,
								'user_id'  => $user->ID,
								'nickname' => $user->display_name,
							);
						}
						return $out;
					},
				),
				// Create or update persona users. Role is always subscriber; nothing else can be set.
				array(
					'methods'             => 'POST',
					'permission_callback' => $can,
					'callback'            => function ( WP_REST_Request $req ) {
						$items = $req->get_json_params()['personas'] ?? null;
						if ( ! is_array( $items ) || ! $items ) {
							return new WP_Error( 'tn_bad_personas', 'personas array required', array( 'status' => 400 ) );
						}
						$existing = tn_persona_users();
						$result   = array();
						foreach ( $items as $p ) {
							$pid  = isset( $p['id'] ) ? sanitize_key( $p['id'] ) : '';
							$nick = isset( $p['nickname'] ) ? sanitize_text_field( $p['nickname'] ) : '';
							if ( ! $pid || ! $nick ) {
								return new WP_Error( 'tn_bad_persona', 'each persona needs id and nickname', array( 'status' => 400 ) );
							}
							$avatar = isset( $p['avatar_url'] ) ? esc_url_raw( $p['avatar_url'] ) : '';
							if ( isset( $existing[ $pid ] ) ) {
								$uid = $existing[ $pid ]->ID;
								wp_update_user( array( 'ID' => $uid, 'display_name' => $nick, 'nickname' => $nick ) );
								$action = 'updated';
							} else {
								$login = TN_PERSONA_PREFIX . $pid;
								if ( username_exists( $login ) ) {
									return new WP_Error( 'tn_login_taken', "user $login exists but is not a persona", array( 'status' => 409 ) );
								}
								$uid = wp_insert_user(
									array(
										'user_login'   => $login,
										'user_pass'    => wp_generate_password( 32, true, true ),
										'user_email'   => $pid . '@' . TN_PERSONA_DOMAIN,
										'display_name' => $nick,
										'nickname'     => $nick,
										'role'         => 'subscriber',
									)
								);
								if ( is_wp_error( $uid ) ) {
									return $uid;
								}
								update_user_meta( $uid, 'tn_persona', $pid );
								$action = 'created';
							}
							if ( $avatar ) {
								update_user_meta( $uid, 'tn_avatar_url', $avatar );
							} else {
								delete_user_meta( $uid, 'tn_avatar_url' );
							}
							$result[] = array( 'persona' => $pid, 'user_id' => $uid, 'nickname' => $nick, 'action' => $action );
						}
						return $result;
					},
				),
			)
		);

		// Comments of one post, with generation meta.
		register_rest_route(
			'the-news/v1',
			'/comments',
			array(
				array(
					'methods'             => 'GET',
					'permission_callback' => $can,
					'args'                => array(
						'post' => array( 'required' => true, 'type' => 'integer' ),
					),
					'callback'            => function ( WP_REST_Request $req ) {
						$comments = get_comments(
							array(
								'post_id' => (int) $req['post'],
								'status'  => 'all',
								'orderby' => 'comment_date_gmt',
								'order'   => 'ASC',
							)
						);
						return array_map( 'tn_comment_payload', $comments );
					},
				),
				// Add one persona comment. Idempotent per (card, ref).
				array(
					'methods'             => 'POST',
					'permission_callback' => $can,
					'callback'            => function ( WP_REST_Request $req ) {
						$p       = $req->get_json_params();
						$post_id = (int) ( $p['post'] ?? 0 );
						$card    = sanitize_text_field( $p['card'] ?? '' );
						$ref     = sanitize_text_field( $p['ref'] ?? '' );
						$pid     = sanitize_key( $p['persona'] ?? '' );
						$content = trim( (string) ( $p['content'] ?? '' ) );
						$parent  = (int) ( $p['parent'] ?? 0 );
						$post    = get_post( $post_id );

						if ( ! $post || 'publish' !== $post->post_status ) {
							return new WP_Error( 'tn_no_post', 'post not found or not published', array( 'status' => 404 ) );
						}
						if ( ! comments_open( $post ) ) {
							return new WP_Error( 'tn_closed', 'comments are closed on this post', array( 'status' => 409 ) );
						}
						if ( ! $card || ! $ref ) {
							return new WP_Error( 'tn_bad_request', 'card and ref required', array( 'status' => 400 ) );
						}
						if ( '' === $content || mb_strlen( $content ) > TN_MAX_CONTENT_CHARS ) {
							return new WP_Error( 'tn_bad_content', 'content empty or too long', array( 'status' => 400 ) );
						}
						$dup = tn_find_generated( $post_id, $card, $ref );
						if ( $dup ) {
							return array( 'skipped' => true, 'comment' => tn_comment_payload( $dup ) );
						}
						$users = tn_persona_users();
						if ( ! isset( $users[ $pid ] ) ) {
							return new WP_Error( 'tn_no_persona', "unknown persona '$pid' (run sync-personas)", array( 'status' => 400 ) );
						}
						if ( $parent ) {
							$pc = get_comment( $parent );
							if ( ! $pc || (int) $pc->comment_post_ID !== $post_id ) {
								return new WP_Error( 'tn_bad_parent', 'parent comment not on this post', array( 'status' => 400 ) );
							}
						}
						$user = $users[ $pid ];
						$ts   = isset( $p['date_gmt'] ) ? strtotime( $p['date_gmt'] ) : false;
						$ts   = ( $ts && $ts <= time() ) ? $ts : time();
						$id   = wp_insert_comment(
							array(
								'comment_post_ID'      => $post_id,
								'comment_parent'       => $parent,
								'comment_content'      => wp_kses( $content, array() ),
								'comment_author'       => $user->display_name,
								'comment_author_email' => $user->user_email,
								'comment_author_url'   => '',
								'user_id'              => $user->ID,
								'comment_approved'     => 1,
								'comment_type'         => 'comment',
								'comment_date_gmt'     => gmdate( 'Y-m-d H:i:s', $ts ),
								'comment_date'         => get_date_from_gmt( gmdate( 'Y-m-d H:i:s', $ts ) ),
								'comment_meta'         => array(
									'_tn_generated' => 1,
									'_tn_persona'   => $pid,
									'_tn_card'      => $card,
									'_tn_ref'       => $ref,
								),
							)
						);
						if ( ! $id ) {
							return new WP_Error( 'tn_insert_failed', 'wp_insert_comment failed', array( 'status' => 500 ) );
						}
						return array( 'skipped' => false, 'comment' => tn_comment_payload( get_comment( $id ) ) );
					},
				),
			)
		);

		/*
		 * Human comments (not generated, not by a persona or tn_commenter account) newer than
		 * after_id, for the reaction watcher. max_id lets the watcher start from "now".
		 */
		register_rest_route(
			'the-news/v1',
			'/user-comments',
			array(
				'methods'             => 'GET',
				'permission_callback' => $can,
				'args'                => array(
					'after_id' => array( 'type' => 'integer', 'default' => 0 ),
				),
				'callback'            => function ( WP_REST_Request $req ) {
					global $wpdb;
					$max_id = (int) $wpdb->get_var( "SELECT MAX(comment_ID) FROM {$wpdb->comments}" );
					$after  = (int) $req['after_id'];
					$out    = array();
					if ( $after > 0 ) {
						$rows = $wpdb->get_col( $wpdb->prepare( "SELECT comment_ID FROM {$wpdb->comments} WHERE comment_ID > %d AND comment_approved = '1' AND comment_type IN ('comment','') ORDER BY comment_ID LIMIT 200", $after ) );
						foreach ( $rows as $cid ) {
							$c = get_comment( $cid );
							if ( ! $c || get_comment_meta( $cid, '_tn_generated', true ) ) {
								continue;
							}
							if ( tn_persona_of_user( $c->user_id ) || ( $c->user_id && user_can( (int) $c->user_id, TN_COMMENTS_CAP ) && ! user_can( (int) $c->user_id, 'manage_options' ) ) ) {
								continue;
							}
							if ( 'publish' !== get_post_status( $c->comment_post_ID ) ) {
								continue;
							}
							$out[] = array(
								'id'      => (int) $cid,
								'post'    => (int) $c->comment_post_ID,
								'parent'  => (int) $c->comment_parent,
								'author'  => $c->comment_author,
								'content' => wp_trim_words( $c->comment_content, 40, '…' ),
							);
						}
					}
					return array( 'max_id' => $max_id, 'comments' => $out );
				},
			)
		);

		// Move generated comments to trash, by post or by card. Never touches user comments.
		register_rest_route(
			'the-news/v1',
			'/comments/purge',
			array(
				'methods'             => 'POST',
				'permission_callback' => $can,
				'callback'            => function ( WP_REST_Request $req ) {
					$p    = $req->get_json_params();
					$meta = array( array( 'key' => '_tn_generated', 'value' => '1' ) );
					$args = array( 'status' => 'all', 'number' => 0 );
					if ( ! empty( $p['card'] ) ) {
						$meta[] = array( 'key' => '_tn_card', 'value' => sanitize_text_field( $p['card'] ) );
					}
					if ( ! empty( $p['post'] ) ) {
						$args['post_id'] = (int) $p['post'];
					}
					if ( count( $meta ) < 2 && empty( $args['post_id'] ) ) {
						return new WP_Error( 'tn_bad_request', 'post or card required', array( 'status' => 400 ) );
					}
					$args['meta_query'] = $meta;
					$trashed            = array();
					foreach ( get_comments( $args ) as $c ) {
						if ( wp_trash_comment( $c ) ) {
							$trashed[] = (int) $c->comment_ID;
						}
					}
					return array( 'trashed' => $trashed );
				},
			)
		);
	}
);

/*
 * Avatars: persona users show tn_avatar_url if set, otherwise a local SVG identicon
 * derived from the persona ID (no external Gravatar request). Markup only; served below.
 */
function tn_identicon_svg( $seed ) {
	$h     = md5( $seed );
	$hue   = hexdec( substr( $h, 0, 3 ) ) % 360;
	$fg    = "hsl($hue,55%,45%)";
	$cells = '';
	for ( $y = 0; $y < 5; $y++ ) {
		for ( $x = 0; $x < 3; $x++ ) {
			if ( hexdec( $h[ 3 + $y * 3 + $x ] ) % 2 ) {
				$cells .= sprintf( '<rect x="%d" y="%d" width="1" height="1"/>', $x, $y );
				if ( $x < 2 ) {
					$cells .= sprintf( '<rect x="%d" y="%d" width="1" height="1"/>', 4 - $x, $y );
				}
			}
		}
	}
	return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="-0.5 -0.5 6 6" shape-rendering="crispEdges">'
		. '<rect x="-0.5" y="-0.5" width="6" height="6" fill="#eef1f5"/><g fill="' . $fg . '">' . $cells . '</g></svg>';
}

// Avatar URLs go through esc_url, which drops data: URIs, so the identicon is served from ?tn_avatar=<persona>.
add_action(
	'init',
	function () {
		if ( ! isset( $_GET['tn_avatar'] ) ) {
			return;
		}
		$pid = sanitize_key( wp_unslash( $_GET['tn_avatar'] ) );
		if ( '' === $pid ) {
			return;
		}
		header( 'Content-Type: image/svg+xml' );
		header( 'Cache-Control: public, max-age=604800' );
		header( 'X-Content-Type-Options: nosniff' );
		echo tn_identicon_svg( $pid ); // phpcs:ignore WordPress.Security.EscapeOutput -- built from a hash only.
		exit;
	},
	0
);

add_filter(
	'pre_get_avatar_data',
	function ( $args, $id_or_email ) {
		$user_id = 0;
		if ( $id_or_email instanceof WP_Comment ) {
			$user_id = (int) $id_or_email->user_id;
		} elseif ( $id_or_email instanceof WP_User ) {
			$user_id = $id_or_email->ID;
		} elseif ( is_numeric( $id_or_email ) ) {
			$user_id = (int) $id_or_email;
		}
		$pid = tn_persona_of_user( $user_id );
		if ( '' === $pid ) {
			return $args;
		}
		$custom      = get_user_meta( $user_id, 'tn_avatar_url', true );
		$args['url'] = $custom ? $custom : add_query_arg( 'tn_avatar', $pid, home_url( '/' ) );
		return $args;
	},
	10,
	2
);

// Persona users have no author page worth linking to.
add_filter(
	'get_comment_author_url',
	function ( $url, $comment_id, $comment ) {
		return ( $comment && tn_persona_of_user( $comment->user_id ) ) ? '' : $url;
	},
	10,
	3
);
