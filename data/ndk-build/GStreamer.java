package com.gstreamer;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;

import android.content.Context;
import android.content.res.AssetManager;

public class GStreamer {
    private static native void nativeInit(Context context) throws Exception;

    public static void init(Context context) throws Exception {
        nativeInit(context);
@INCLUDE_FONTS@        copyFonts(context);
    }

@INCLUDE_FONTS@    private static void copyFonts(Context context) {
@INCLUDE_FONTS@        AssetManager assetManager = context.getAssets();
@INCLUDE_FONTS@        File filesDir = context.getFilesDir();
@INCLUDE_FONTS@        File fontsFCDir = new File (filesDir, "fontconfig");
@INCLUDE_FONTS@        File fontsDir = new File (fontsFCDir, "fonts");
@INCLUDE_FONTS@        File fontsCfg = new File (fontsFCDir, "fonts.conf");
@INCLUDE_FONTS@
@INCLUDE_FONTS@        fontsDir.mkdirs();
@INCLUDE_FONTS@
@INCLUDE_FONTS@        try {
@INCLUDE_FONTS@            /* Copy the config file */
@INCLUDE_FONTS@            copyFile (assetManager, "fontconfig/fonts.conf", fontsCfg);
@INCLUDE_FONTS@            /* Copy the fonts */
@INCLUDE_FONTS@            for(String filename : assetManager.list("fontconfig/fonts/truetype")) {
@INCLUDE_FONTS@                File font = new File(fontsDir, filename);
@INCLUDE_FONTS@                copyFile (assetManager, "fontconfig/fonts/truetype/" + filename, font);
@INCLUDE_FONTS@            }
@INCLUDE_FONTS@        } catch (IOException e) {
@INCLUDE_FONTS@            e.printStackTrace();
@INCLUDE_FONTS@        }
@INCLUDE_FONTS@    }

@INCLUDE_COPY_FILE@    private static void copyFile(AssetManager assetManager, String assetPath, File outFile) throws IOException {
@INCLUDE_COPY_FILE@        InputStream in;
@INCLUDE_COPY_FILE@        OutputStream out;
@INCLUDE_COPY_FILE@        byte[] buffer = new byte[1024];
@INCLUDE_COPY_FILE@        int read;
@INCLUDE_COPY_FILE@
@INCLUDE_COPY_FILE@        if (outFile.exists())
@INCLUDE_COPY_FILE@            return;
@INCLUDE_COPY_FILE@
@INCLUDE_COPY_FILE@        in = assetManager.open(assetPath);
@INCLUDE_COPY_FILE@        out = new FileOutputStream (outFile);
@INCLUDE_COPY_FILE@        while((read = in.read(buffer)) != -1){
@INCLUDE_COPY_FILE@          out.write(buffer, 0, read);
@INCLUDE_COPY_FILE@        }
@INCLUDE_COPY_FILE@        in.close();
@INCLUDE_COPY_FILE@        out.flush();
@INCLUDE_COPY_FILE@        out.close();
@INCLUDE_COPY_FILE@   }
}
