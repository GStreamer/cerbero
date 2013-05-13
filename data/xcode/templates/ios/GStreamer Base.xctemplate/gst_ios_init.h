#ifndef __GST_IOS_INIT_H__
#define __GST_IOS_INIT_H__

#include <gst/gst.h>

G_BEGIN_DECLS

/* Uncomment each line to enable the plugin categories that your application needs.
 * You can also enable individual plugins. See gst_ios_init.c to see their names
 */

@GST_IOS_PLUGINS_CATEGORIES@

void gst_ios_init ();

G_END_DECLS

#endif
