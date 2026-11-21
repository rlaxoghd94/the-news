/* The News: featured slider controls and month headings for the post list. */
( function () {
	'use strict';

	/* Featured posts: manual slider (buttons, dots, swipe, arrow keys). No autoplay. */
	function initSlider( root ) {
		var track = root.querySelector( '.tn-track' );
		if ( ! track ) {
			return;
		}
		var slides = Array.prototype.slice.call( track.children );
		var title = root.querySelector( '.tn-feat-title' );
		root.setAttribute( 'aria-roledescription', 'carousel' );
		root.setAttribute( 'aria-label', '대표 글' );
		track.setAttribute( 'tabindex', '0' );
		slides.forEach( function ( s, k ) {
			s.setAttribute( 'aria-roledescription', 'slide' );
			s.setAttribute( 'aria-label', ( k + 1 ) + ' / ' + slides.length );
		} );
		if ( slides.length < 2 ) {
			return;
		}

		var head = document.createElement( 'div' );
		head.className = 'tn-feat-head';
		title.parentNode.insertBefore( head, title );
		head.appendChild( title );
		var ctrl = document.createElement( 'div' );
		ctrl.className = 'tn-ctrl';
		ctrl.innerHTML =
			'<button type="button" class="tn-prev" aria-label="이전 대표 글">‹</button>' +
			'<span class="tn-pos"></span>' +
			'<button type="button" class="tn-next" aria-label="다음 대표 글">›</button>';
		head.appendChild( ctrl );

		var dots = document.createElement( 'div' );
		dots.className = 'tn-dots';
		slides.forEach( function ( s, k ) {
			var b = document.createElement( 'button' );
			b.type = 'button';
			b.setAttribute( 'aria-label', ( k + 1 ) + '번째 대표 글 보기' );
			b.addEventListener( 'click', function () { go( k ); } );
			dots.appendChild( b );
		} );
		track.parentNode.insertBefore( dots, track.nextSibling );

		var prev = ctrl.querySelector( '.tn-prev' );
		var next = ctrl.querySelector( '.tn-next' );
		var pos = ctrl.querySelector( '.tn-pos' );
		var reduce = window.matchMedia( '(prefers-reduced-motion: reduce)' ).matches;
		var i = 0;
		var gap = parseFloat( getComputedStyle( track ).columnGap ) || 0;

		function step() {
			return slides[ 0 ].getBoundingClientRect().width + gap;
		}
		function go( n ) {
			n = Math.max( 0, Math.min( slides.length - 1, n ) );
			track.scrollTo( { left: n * step(), behavior: reduce ? 'auto' : 'smooth' } );
		}
		function sync() {
			i = Math.round( track.scrollLeft / step() );
			pos.textContent = ( i + 1 ) + ' / ' + slides.length;
			Array.prototype.forEach.call( dots.children, function ( d, k ) {
				d.setAttribute( 'aria-current', k === i ? 'true' : 'false' );
			} );
			prev.disabled = i === 0;
			next.disabled = i === slides.length - 1;
		}
		prev.addEventListener( 'click', function () { go( i - 1 ); } );
		next.addEventListener( 'click', function () { go( i + 1 ); } );
		track.addEventListener( 'keydown', function ( e ) {
			if ( e.key === 'ArrowRight' ) { e.preventDefault(); go( i + 1 ); }
			if ( e.key === 'ArrowLeft' ) { e.preventDefault(); go( i - 1 ); }
		} );
		track.addEventListener( 'scroll', function () { window.requestAnimationFrame( sync ); }, { passive: true } );
		window.addEventListener( 'resize', sync );
		sync();
	}

	/* Post list: insert a "YYYY년 M월" heading row before each month's first post. */
	function addMonths( list ) {
		var last = '';
		Array.prototype.slice.call( list.children ).forEach( function ( li ) {
			var t = li.querySelector( '.tn-day time[datetime]' );
			if ( ! t ) {
				return;
			}
			var d = t.getAttribute( 'datetime' ).slice( 0, 7 );
			if ( d === last ) {
				return;
			}
			last = d;
			var h = document.createElement( 'li' );
			h.className = 'tn-month';
			h.setAttribute( 'role', 'presentation' );
			h.textContent = d.slice( 0, 4 ) + '년 ' + parseInt( d.slice( 5 ), 10 ) + '월';
			list.insertBefore( h, li );
		} );
	}

	function init() {
		document.querySelectorAll( '.tn-feature' ).forEach( initSlider );
		document.querySelectorAll( '.tn-list .tn-items' ).forEach( addMonths );
	}
	if ( document.readyState === 'loading' ) {
		document.addEventListener( 'DOMContentLoaded', init );
	} else {
		init();
	}
} )();
