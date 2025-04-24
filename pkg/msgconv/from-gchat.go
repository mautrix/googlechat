package msgconv

import (
	"context"
	"io"
	"log"
	"mime"
	"net/url"
	"strings"

	"maunium.net/go/mautrix/bridgev2"
	"maunium.net/go/mautrix/bridgev2/networkid"
	bridgeEvt "maunium.net/go/mautrix/event"

	"go.mau.fi/util/ptr"

	"go.mau.fi/mautrix-googlechat/pkg/gchatmeow/proto"
	"go.mau.fi/mautrix-googlechat/pkg/msgconv/gchatfmt"
)

func (mc *MessageConverter) ToMatrix(ctx context.Context, portal *bridgev2.Portal, intent bridgev2.MatrixAPI, msg *proto.Message) (*bridgev2.ConvertedMessage, error) {
	parts := make([]*bridgev2.ConvertedMessagePart, 0)

	textContent := gchatfmt.Parse(ctx, portal, msg)
	if textContent != nil {
		textPart := &bridgev2.ConvertedMessagePart{
			ID:      "",
			Type:    bridgeEvt.EventMessage,
			Content: textContent,
		}
		parts = append(parts, textPart)
	}

	for _, annotation := range msg.Annotations {
		attachmentPart, err := mc.gcAnnotationToMatrix(ctx, portal, intent, annotation)
		if err != nil {
			log.Printf("[msgconv:from-gchat]: failed to convert annotation to matrix: %#v", err)
			continue
		}
		if attachmentPart != nil {
			parts = append(parts, attachmentPart)
		}
	}

	cm := &bridgev2.ConvertedMessage{
		Parts: parts,
	}

	parentId := msg.Id.ParentId.GetTopicId().TopicId
	if parentId != "" {
		cm.ThreadRoot = ptr.Ptr(networkid.MessageID(parentId))
	}
	if msg.ReplyTo != nil {
		replyTo := msg.ReplyTo.Id.MessageId
		if replyTo != "" {
			cm.ReplyTo = &networkid.MessageOptionalPartID{MessageID: networkid.MessageID(replyTo)}
		}
	}

	cm.MergeCaption()

	return cm, nil
}

func (mc *MessageConverter) gcAnnotationToMatrix(ctx context.Context, portal *bridgev2.Portal, intent bridgev2.MatrixAPI, annotation *proto.Annotation) (*bridgev2.ConvertedMessagePart, error) {
	var attUrl *url.URL
	var mimeType string
	var fileName string
	uploadMeta := annotation.GetUploadMetadata()
	urlMeta := annotation.GetUrlMetadata()
	if uploadMeta != nil {
		mimeType = uploadMeta.ContentType
		fileName = uploadMeta.ContentName
		params := url.Values{
			"url_type":         []string{"DOWNLOAD_URL"},
			"attachment_token": []string{uploadMeta.GetAttachmentToken()},
		}
		if strings.HasPrefix(uploadMeta.ContentType, "image/") {
			params.Set("url_type", "FIFE_URL")
			params.Set("sz", "w10000-h10000")
			params.Set("content_type", uploadMeta.ContentType)
		}
		parsedUrl, err := url.Parse("https://chat.google.com/api/get_attachment_url")
		if err != nil {
			return nil, err
		}
		attUrl = parsedUrl
		attUrl.RawQuery = params.Encode()

	} else if urlMeta != nil {
		if urlMeta.MimeType != "" {
			mimeType = urlMeta.MimeType
		}
		parsedUrl, err := url.Parse(urlMeta.Url.Url)
		if err != nil {
			return nil, err
		}
		attUrl = parsedUrl
	} else {
		return nil, nil
	}
	resp, err := mc.client.DownloadAttachment(ctx, attUrl)
	if err != nil {
		return nil, err
	}

	if fileName == "" {
		_, params, _ := mime.ParseMediaType(resp.Header.Get("Content-Disposition"))
		fileName = params["filename"]
	}
	if mimeType == "" {
		mimeType = resp.Header.Get("Content-Type")
	}
	if fileName == "" && mimeType != "" {
		fileName = strings.Replace(mimeType, "/", ".", 1)
	}

	content := bridgeEvt.MessageEventContent{
		Body: fileName,
		Info: &bridgeEvt.FileInfo{
			MimeType: mimeType,
		},
		MsgType: bridgeEvt.MsgImage,
	}
	content.URL, content.File, err = intent.UploadMediaStream(ctx, portal.MXID, resp.ContentLength, true, func(file io.Writer) (*bridgev2.FileStreamResult, error) {
		_, err := io.Copy(file, resp.Body)
		if err != nil {
			return nil, err
		}
		return &bridgev2.FileStreamResult{
			MimeType: content.Info.MimeType,
			FileName: fileName,
		}, nil
	})
	if err != nil {
		return nil, err
	}
	return &bridgev2.ConvertedMessagePart{
		ID:      "",
		Type:    bridgeEvt.EventMessage,
		Content: &content,
	}, nil
}
