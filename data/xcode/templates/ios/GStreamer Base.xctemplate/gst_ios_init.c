#include "gst_ios_init.h"

@GST_IOS_PLUGINS_DECLARE@

void
gst_ios_init (void)
{
  gst_init (NULL, NULL);

  @GST_IOS_PLUGINS_REGISTER@
}
