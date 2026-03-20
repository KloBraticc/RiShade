using Avalonia;
using Avalonia.Animation;
using Avalonia.Animation.Easings;
using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Media;
using Avalonia.Styling;
using Avalonia.Threading;
using Avalonia.VisualTree;
using Rishade.Views.Animations;
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Reflection;
using System.Threading;
using System.Threading.Tasks;

namespace Rishade.Views
{
    public partial class MainWindow : Window
    {
        private readonly Dictionary<Control, FrameAnimator?> _activeAnimations = new();
        private readonly Dictionary<Control, IDisposable?> _pendingSlideDownTimers = new();
        private readonly Dictionary<string, Control> _pageCache = new();
        private bool _isPageLoading = false;
        private bool _snackbarResetting;
        private bool _resetting;

        public MainWindow()
        {
            InitializeComponent();

#if DEBUG
    this.AttachDevTools();
#endif

            NavIndicator.Background = Brushes.DarkGray;
            if (Application.Current.Resources.TryGetResource("ThemeAccentBrush", null, out var brushObj))
            {
                if (brushObj is IBrush brush)
                    NavIndicator.Background = brush;
            }

            var HomePage = new Home();
            MainContent.Content = HomePage;
            var defaultItem = NavList.Items
                .OfType<ListBoxItem>()
                .FirstOrDefault(i => i.Tag?.ToString() == "Home");

            if (defaultItem != null)
            {
                NavList.SelectedItem = defaultItem;
                defaultItem.AttachedToVisualTree += async (s, e) =>
                {
                    await Task.Delay(10);
                    await UpdateIndicator(defaultItem);
                };
            }

            NavList.SelectionChanged += (s, e) =>
            {
                if (NavList.SelectedIndex >= 0)
                {
                    var selectedContainer = NavList.ItemContainerGenerator.ContainerFromIndex(NavList.SelectedIndex) as ListBoxItem;
                    if (selectedContainer != null)
                        UpdateIndicator(selectedContainer);
                }
            };
        }

        private void TitleBar_PointerPressed(object sender, Avalonia.Input.PointerPressedEventArgs e)
        {
            if (e.GetCurrentPoint(this).Properties.IsLeftButtonPressed)
            {
                this.BeginMoveDrag(e);
            }
        }

        private void Disc_Click(object? sender, Avalonia.Input.PointerPressedEventArgs e)
        {
            OpenUrl("https://discord.gg/5tJBqBH8ck");
        }

        private void GitHub_Click(object? sender, Avalonia.Input.PointerPressedEventArgs e)
        {
            OpenUrl("https://github.com/KloBraticc/RiShade");
        }

        private void OpenUrl(string url)
        {
            try
            {
                Process.Start(new ProcessStartInfo
                {
                    FileName = url,
                    UseShellExecute = true
                });
            }
            catch
            {}
        }

        private void StartAutoHide(Control snackbar)
        {
            var transform = (TranslateTransform)snackbar.RenderTransform;

            var timer = DispatcherTimer.RunOnce(() =>
            {
                var slideDown = new FrameAnimator(140,
                    t => transform.Y = Lerp(0, 70, t),
                    () =>
                    {
                        transform.Y = 70;
                        snackbar.Opacity = 0;
                    });

                _activeAnimations[snackbar] = slideDown;
                slideDown.Start();

            }, TimeSpan.FromMilliseconds(3000));

            _pendingSlideDownTimers[snackbar] = timer;
        }

        private void SlideSnackbar(Control snackbar, double fromY, double toY, int durationMs, Action? completed = null)
        {
            if (snackbar.RenderTransform is not TranslateTransform transform)
                return;

            var animator = new FrameAnimator(durationMs,
                t =>
                {
                    transform.Y = Lerp(fromY, toY, t);
                },
                completed);

            animator.Start();
        }

        private double Lerp(double from, double to, double t)
            => from + (to - from) * t;

        private void NavList_SelectionChanged(object? sender, SelectionChangedEventArgs e)
        {
            if (NavList.SelectedItem is ListBoxItem item)
            {
                Control? newPage = item.Tag?.ToString() switch
                {
                    "Home" => new Home(),
                    _ => null
                };

                if (newPage != null)
                {
                    MainContent.Content = newPage;
                    Rishade.Views.Animations.Transitions.ApplyTransition(newPage, Rishade.Views.Animations.TransitionType.SlideRight, 350);
                }
                else
                {
                    MainContent.Content = null;
                }
            }
        }

        private void Closebutton(object sender, RoutedEventArgs e)
        {
            this.Close();
        }

        private void CloseInfoBar(object? sender, RoutedEventArgs e)
        {
            var infoBarBorder = this.FindControl<Border>("InfoBarBorder");
            if (infoBarBorder != null)
                infoBarBorder.IsVisible = false;
        }

        private async Task UpdateIndicator(ListBoxItem item)
        {
            if (item == null) return;
            var pos = item.TransformToVisual(NavList)?.Transform(new Point(0, 0));
            if (pos == null) return;

            double indicatorHeight = item.Bounds.Height * 0.6;
            double topOffset = pos.Value.Y + (item.Bounds.Height - indicatorHeight) / 2;
            NavIndicator.Margin = new Avalonia.Thickness(0, topOffset, 0, 0);
            NavIndicator.Height = indicatorHeight;

            var fade = new Animation
            {
                Duration = TimeSpan.FromMilliseconds(200),
                Easing = new QuadraticEaseOut(),
                Children =
        {
            new KeyFrame
            {
                Cue = new Cue(0),
                Setters = { new Setter(Border.OpacityProperty, 0.0) }
            },
            new KeyFrame
            {
                Cue = new Cue(1),
                Setters = { new Setter(Border.OpacityProperty, 1.0) }
            }
        }
            };

            await fade.RunAsync(NavIndicator, CancellationToken.None);
            NavIndicator.Opacity = 1;
        }
    }
}