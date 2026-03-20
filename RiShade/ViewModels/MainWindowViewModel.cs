using System;
using System.Windows.Input;
using Avalonia.Controls;

namespace Rishade.ViewModels
{
    public partial class MainWindowViewModel : ViewModelBase
    {
        public ICommand OpenAboutCommand { get; }

        public MainWindowViewModel()
        {
        }
    }
}