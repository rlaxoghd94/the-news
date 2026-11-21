<?php
/**
 * The News theme setup.
 *
 * @package the-news
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

const THE_NEWS_VERSION = '0.1.0';

/**
 * Fonts and theme assets (front end and editor).
 */
function the_news_fonts_url() {
	return 'https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;600;700&display=swap';
}

add_action(
	'wp_enqueue_scripts',
	function () {
		wp_enqueue_style( 'the-news-fonts', the_news_fonts_url(), array(), null );
		wp_enqueue_style( 'the-news', get_theme_file_uri( 'assets/css/theme.css' ), array(), THE_NEWS_VERSION );
		wp_enqueue_script(
			'the-news',
			get_theme_file_uri( 'assets/js/theme.js' ),
			array(),
			THE_NEWS_VERSION,
			array(
				'in_footer' => true,
				'strategy'  => 'defer',
			)
		);
	}
);

add_action(
	'after_setup_theme',
	function () {
		add_theme_support( 'editor-styles' );
		add_editor_style( array( the_news_fonts_url(), 'assets/css/theme.css' ) );
	}
);

/**
 * Home: sticky posts appear only in the featured slider, so the main list
 * leaves them out and keeps normal pagination.
 */
add_action(
	'pre_get_posts',
	function ( $query ) {
		if ( is_admin() || ! $query->is_main_query() || ! $query->is_home() ) {
			return;
		}
		$sticky = get_option( 'sticky_posts' );
		if ( ! empty( $sticky ) ) {
			$query->set( 'post__not_in', array_map( 'intval', $sticky ) );
		}
		$query->set( 'ignore_sticky_posts', true );
	}
);

/**
 * Block render adjustments.
 */
add_filter(
	'render_block',
	function ( $content, $block ) {
		$class = $block['attrs']['className'] ?? '';

		// Featured slider: render nothing when there are no sticky posts.
		if ( 'core/query' === $block['blockName'] && str_contains( $class, 'tn-feature' ) ) {
			if ( empty( get_option( 'sticky_posts' ) ) || ! str_contains( $content, 'wp-block-post ' ) ) {
				return '';
			}
		}

		// Sidebar "소개": hide the whole section when the site tagline is empty.
		if ( 'core/group' === $block['blockName'] && str_contains( $class, 'tn-sb-about' ) && '' === trim( get_bloginfo( 'description' ) ) ) {
			return '';
		}

		// Featured slider images sit above the fold: load them right away.
		if ( 'core/post-featured-image' === $block['blockName'] && str_contains( $class, 'tn-slide-img' ) ) {
			$content = str_replace( 'loading="lazy"', 'loading="eager"', $content );
		}

		// Standfirst: only a hand-written excerpt, never the automatic one.
		if ( 'core/post-excerpt' === $block['blockName'] && str_contains( $class, 'tn-standfirst' ) && ! has_excerpt() ) {
			return '';
		}

		// Featured image on a single post: add the media caption when present.
		if ( 'core/post-featured-image' === $block['blockName'] && str_contains( $class, 'tn-hero-img' ) && '' !== trim( $content ) ) {
			$caption = wp_get_attachment_caption( get_post_thumbnail_id() );
			if ( $caption ) {
				$content = preg_replace(
					'#</figure>\s*$#',
					'<figcaption class="wp-element-caption">' . wp_kses_post( $caption ) . '</figcaption></figure>',
					$content
				);
			}
		}

		return $content;
	},
	10,
	2
);

/**
 * Reading time as a block binding: a paragraph bound to the-news/reading-time
 * shows "N분 분량" for the post in context (about 500 Korean characters a minute).
 */
add_action(
	'init',
	function () {
		if ( ! function_exists( 'register_block_bindings_source' ) ) {
			return;
		}
		register_block_bindings_source(
			'the-news/reading-time',
			array(
				'label'              => __( '읽는 시간', 'the-news' ),
				'uses_context'       => array( 'postId' ),
				'get_value_callback' => function ( $source_args, $block_instance ) {
					$post_id = $block_instance->context['postId'] ?? get_the_ID();
					$text    = wp_strip_all_tags( strip_shortcodes( get_post_field( 'post_content', $post_id ) ) );
					$chars   = mb_strlen( preg_replace( '/\s+/u', '', $text ) );
					$minutes = max( 1, (int) ceil( $chars / 500 ) );
					/* translators: %d: minutes */
					return sprintf( __( '%d분 분량', 'the-news' ), $minutes );
				},
			)
		);
	}
);

/**
 * Pattern category for the article helpers (sources, process box).
 */
add_action(
	'init',
	function () {
		register_block_pattern_category( 'the-news', array( 'label' => __( 'The News', 'the-news' ) ) );
	}
);

/**
 * Automatic excerpts: Korean words are long, so keep the list summary short.
 */
add_filter(
	'excerpt_length',
	function () {
		return 32;
	}
);
add_filter(
	'excerpt_more',
	function () {
		return '…';
	}
);
