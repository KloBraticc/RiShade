using Avalonia;
using Avalonia.Controls;
using Avalonia.Media;
using Avalonia.Threading;
using System;
using System.Diagnostics;
using System.Threading.Tasks;

namespace Rishade.Views.Animations
{
    // this animation frame animator was ported from the WPF UI animation file, this code isnt really mine.
    public static class AnimationState
    {
        public static bool IsLoading { get; set; }
    }

    internal static class Easings
    {
        public static double Smooth(double t)
        {
            t = t * t * (3 - 2 * t);
            return t + Math.Sin(t * Math.PI) * 0.05;
        }

        public static double Fade(double t)
        {
            return t * t * (3 - 2 * t);
        }
    }

    internal sealed class FrameAnimator
    {
        private readonly Action<double> _update;
        private readonly Action? _completed;
        private readonly double _durationMs;
        private readonly Stopwatch _stopwatch;
        private bool _isCanceled;

        public FrameAnimator(double durationMs, Action<double> update, Action? completed = null)
        {
            _durationMs = durationMs;
            _update = update;
            _completed = completed;
            _stopwatch = new Stopwatch();
        }

        public void Start()
        {
            _stopwatch.Restart();
            _isCanceled = false;
            AnimateFrame();
        }
        public void Cancel()
        {
            _isCanceled = true;
        }

        private void AnimateFrame()
        {
            if (_isCanceled)
                return;

            double t = Math.Min(1.0, _stopwatch.Elapsed.TotalMilliseconds / _durationMs);
            _update(t);

            if (t < 1.0)
            {
                Dispatcher.UIThread.Post(AnimateFrame, DispatcherPriority.Render);
            }
            else
            {
                _completed?.Invoke();
            }
        }
    }

    public enum TransitionType
    {
        None,
        FadeIn,
        SlideLeft,
        SlideRight,
        SlideBottom,
        FadeInWithSlide,
        FadeInWithSlideRight
    }

    public static class Transitions
    {
        private const int MinDuration = 260;
        private const int MaxDuration = 1250;

        public static Task ApplyTransition(Control element, TransitionType type, int duration = 300)
        {
            if (type == TransitionType.None || element == null || AnimationState.IsLoading)
                return Task.CompletedTask;

            duration = Math.Clamp(duration, MinDuration, MaxDuration);

            var tcs = new TaskCompletionSource<bool>();

            void Completed() => tcs.TrySetResult(true);

            switch (type)
            {
                case TransitionType.FadeIn:
                    FadeIn(element, duration, Completed);
                    break;
                case TransitionType.SlideLeft:
                    Slide(element, -50, 0, duration, true, Completed);
                    break;
                case TransitionType.SlideRight:
                    Slide(element, 50, 0, duration, true, Completed);
                    break;
                case TransitionType.SlideBottom:
                    Slide(element, 0, 40, duration, true, Completed);
                    break;
                default:
                    tcs.SetResult(true);
                    break;
            }

            return tcs.Task;
        }

        private static void FadeIn(Control element, int durationMs, Action completed)
        {
            element.Opacity = 0;

            var animator = new FrameAnimator(
                durationMs,
                t => element.Opacity = Easings.Fade(t),
                () =>
                {
                    element.Opacity = 1;
                    completed?.Invoke();
                });

            animator.Start();
        }

        private static void Slide(Control element, double offsetX, double offsetY, int durationMs, bool fade, Action completed)
        {
            if (element.RenderTransform == null)
                element.RenderTransform = new TranslateTransform();

            if (fade)
                element.Opacity = 0;

            var transform = (TranslateTransform)element.RenderTransform;

            var animator = new FrameAnimator(
                durationMs,
                t =>
                {
                    var eased = Easings.Smooth(t);
                    transform.X = Lerp(offsetX, 0, eased);
                    transform.Y = Lerp(offsetY, 0, eased);
                    if (fade)
                        element.Opacity = Easings.Fade(t);
                },
                () =>
                {
                    transform.X = 0;
                    transform.Y = 0;
                    element.Opacity = 1;
                    completed?.Invoke();
                });

            animator.Start();
        }

        private static double Lerp(double from, double to, double t)
            => from + (to - from) * t;
    }
}