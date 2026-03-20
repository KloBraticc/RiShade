using Avalonia;
using Avalonia.Controls;
using Avalonia.Styling;
using Avalonia.Animation;
using Avalonia.Collections;

namespace YourApp.Controls
{
    public class StaticButton : Button
    {
        public StaticButton()
        {
            Transitions = new Transitions();

            FocusAdorner = null;
            this.Classes.Remove(":pointerover");
            this.Classes.Remove(":pressed");
        }
    }
}